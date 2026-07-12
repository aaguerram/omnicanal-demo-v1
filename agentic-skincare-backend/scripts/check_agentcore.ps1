# Comprueba que el runtime de AgentCore esta desplegado y, por defecto, hace
# una invocacion real para validar que el endpoint procesa solicitudes.
#
# Uso desde agentic-skincare-backend:
#   .\scripts\check_agentcore.ps1
#   .\scripts\check_agentcore.ps1 -SkipInvoke   # solo estado, sin consumir modelo

[CmdletBinding()]
param(
    [switch]$SkipInvoke,
    [string]$AgentName = "agentic_skincare_backend"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:AGENTCORE_SUPPRESS_RECOMMENDATION = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

# pip --user instala normalmente agentcore.exe fuera del PATH de PowerShell.
$userScripts = Join-Path $env:APPDATA "Python\Python312\Scripts"
if ((Test-Path $userScripts) -and ($env:PATH -notlike "*$userScripts*")) {
    $env:PATH = "$userScripts;$env:PATH"
}

if (-not (Get-Command agentcore -ErrorAction SilentlyContinue)) {
    Write-Error "No se encontro agentcore CLI. Instala bedrock-agentcore-starter-toolkit."
    exit 2
}

Write-Host "Consultando runtime y endpoint de AgentCore..." -ForegroundColor Cyan
$statusText = (& agentcore status --agent $AgentName --verbose 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
    Write-Error "No se pudo consultar AgentCore:`n$statusText"
    exit 3
}

# La salida contiene JSON mas avisos informativos; validar los dos estados
# READY evita depender de deserializar texto adicional emitido por el toolkit.
$readyMatches = [regex]::Matches($statusText, '"status"\s*:\s*"READY"').Count
if ($readyMatches -lt 2) {
    Write-Error "AgentCore no esta listo: runtime y endpoint deben estar READY.`n$statusText"
    exit 4
}

$versionMatch = [regex]::Match($statusText, '"agentRuntimeVersion"\s*:\s*"([^\"]+)"')
$imageMatch = [regex]::Match($statusText, '"containerUri"\s*:\s*"([^\"]+)"')
$version = if ($versionMatch.Success) { $versionMatch.Groups[1].Value } else { "desconocida" }
$image = if ($imageMatch.Success) { $imageMatch.Groups[1].Value } else { "desconocida" }

Write-Host "OK: runtime READY y endpoint READY." -ForegroundColor Green
Write-Host "Version: $version"
Write-Host "Imagen:  $image"

if ($SkipInvoke) {
    Write-Host "Invocacion omitida por -SkipInvoke."
    exit 0
}

Write-Host "Ejecutando prueba real del endpoint..." -ForegroundColor Cyan
$sessionId = [guid]::NewGuid().ToString()
$payload = @{ contact_id = $sessionId; message = "Hola, prueba de disponibilidad" } |
    ConvertTo-Json -Compress
$invokeText = (& agentcore invoke --agent $AgentName --session-id $sessionId $payload 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
    Write-Error "El runtime esta desplegado, pero la invocacion fallo:`n$invokeText"
    exit 5
}

if ($invokeText -notmatch 'response_text') {
    Write-Error "AgentCore respondio, pero no devolvio el contrato esperado (response_text):`n$invokeText"
    exit 6
}

Write-Host "OK: AgentCore esta desplegado, READY y ejecutando solicitudes." -ForegroundColor Green
Write-Host "SessionId de prueba: $sessionId"
exit 0
