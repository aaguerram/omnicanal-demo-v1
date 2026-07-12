# Provisions the 4 intent-based queues and the single shared routing profile
# described in the queues/flows plan (channel is a contact attribute, not a
# queue). Safe to inspect before running: it only creates queues + a routing
# profile, both plain/stable AWS CLI surfaces.
#
# There is no "unrecognized input" queue: F_Menu_Router loops back to its own
# menu prompt when the customer's input doesn't match 1-4, instead of routing
# to a fallback queue.
#
# Contact flows (F_Entrada_Omnicanal, F_Menu_Router, F_IA_*, F_Handoff_Humano,
# F_Espera_Cola) are provisioned separately once the flow JSON is validated
# against the real API — see scripts/provision_connect_flows.ps1.
#
# Idempotent-ish: safe to re-run individual sections, but create-* calls will
# fail loudly if the resource already exists.
#
# Run from the project root: .\scripts\provision_queues_routing.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$Aws = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
$Region = "us-east-1"
$InstanceId = "1029ff15-e0f3-4b9c-bab2-377c17509765"
$RoutingProfileName = "RP_Asesores_Mensajeria_Omnicanal"

$Queues = @(
    @{ Name = "Q_Atencion"; Description = "Consultas generales detectadas como atencion"; Priority = 2 },
    @{ Name = "Q_Soporte"; Description = "Soporte tecnico o funcional"; Priority = 1 },
    @{ Name = "Q_Ventas"; Description = "Interes comercial, cotizaciones, productos"; Priority = 2 },
    @{ Name = "Q_Cobranza"; Description = "Pagos, deuda, recordatorios, acuerdos"; Priority = 1 }
)

# 1. Reuse the instance's existing hours of operation (a small pilot doesn't
# need a bespoke schedule per queue).
$hoursList = & $Aws connect list-hours-of-operations `
    --instance-id $InstanceId --region $Region | ConvertFrom-Json
$hoursOfOperationId = $hoursList.HoursOfOperationSummaryList[0].Id
Write-Host "Using hours of operation: $($hoursList.HoursOfOperationSummaryList[0].Name) ($hoursOfOperationId)"

# 2. Create the 4 queues.
$queueIds = @{}
foreach ($q in $Queues) {
    $result = & $Aws connect create-queue `
        --instance-id $InstanceId `
        --name $q.Name `
        --description $q.Description `
        --hours-of-operation-id $hoursOfOperationId `
        --region $Region | ConvertFrom-Json
    $queueIds[$q.Name] = $result.QueueId
    Write-Host "Created queue $($q.Name): $($result.QueueId)"
}

# 3. Create the shared routing profile (chat-only concurrency for this pilot).
# JSON args are written to temp files and passed via file:// -- PowerShell 5.1
# mangles embedded double quotes when a JSON string is passed inline to a
# native exe like aws.exe.
$defaultOutboundQueueId = $queueIds["Q_Atencion"]
$mediaConcurrenciesFile = New-TemporaryFile
Set-Content -Path $mediaConcurrenciesFile -Value '[{"Channel":"CHAT","Concurrency":5}]' -Encoding ascii -NoNewline

$rp = & $Aws connect create-routing-profile `
    --instance-id $InstanceId `
    --name $RoutingProfileName `
    --description "Pool unico de asesores para atencion, soporte, ventas y cobranza via mensajeria" `
    --default-outbound-queue-id $defaultOutboundQueueId `
    --media-concurrencies "file://$mediaConcurrenciesFile" `
    --region $Region | ConvertFrom-Json
Remove-Item $mediaConcurrenciesFile
if (-not $rp.RoutingProfileId) { throw "create-routing-profile failed -- see aws.exe error above." }
Write-Host "Created routing profile $RoutingProfileName : $($rp.RoutingProfileId)"

# 4. Associate the 4 queues to the routing profile with their priorities.
$queueConfigs = @($Queues | ForEach-Object {
    @{
        QueueReference = @{ QueueId = $queueIds[$_.Name]; Channel = "CHAT" }
        Priority        = $_.Priority
        Delay           = 0
    }
})
$queueConfigsFile = New-TemporaryFile
Set-Content -Path $queueConfigsFile -Value ($queueConfigs | ConvertTo-Json -Depth 5) -Encoding ascii -NoNewline

& $Aws connect associate-routing-profile-queues `
    --instance-id $InstanceId `
    --routing-profile-id $rp.RoutingProfileId `
    --queue-configs "file://$queueConfigsFile" `
    --region $Region
Remove-Item $queueConfigsFile

Write-Host "`nQueue IDs (needed by scripts/provision_connect_flows.ps1):"
$queueIds.GetEnumerator() | ForEach-Object { Write-Host "  $($_.Key) = $($_.Value)" }
Write-Host "Routing profile ID: $($rp.RoutingProfileId)"
