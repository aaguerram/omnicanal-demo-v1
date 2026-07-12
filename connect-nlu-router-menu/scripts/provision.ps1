# One-time provisioning of the AWS resources behind connect-nlu-router-menu:
# the IAM execution role (see infra/trust-policy.json and
# infra/permissions-policy.json) and the Lambda function itself.
#
# Todavia nadie invoca esta funcion (ver README.md, "Estado de la
# integracion"), asi que este script no crea ningun trigger (SNS, API
# Gateway, event source mapping, etc.) -- solo el rol y la funcion. Cuando se
# conecte un caller real (p. ej. telegram-inbound-adapter via
# lambda:InvokeFunction), agregar el permiso correspondiente en ese momento.
#
# Idempotent-ish: safe to re-run individual sections, but create-* calls will
# fail loudly if the resource already exists (that's intentional, so you
# don't silently overwrite a live resource).
#
# Run from the project root: .\scripts\provision.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$Aws = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
$Region = "us-east-1"
$AccountId = "042278586355"
$FunctionName = "connect-nlu-router-menu"
$RoleName = "connect-nlu-router-menu-lambda-role"

# 1. IAM role + inline policy.
& $Aws iam create-role `
    --role-name $RoleName `
    --assume-role-policy-document "file://$root\infra\trust-policy.json" `
    --description "Execution role for connect-nlu-router-menu Lambda"

& $Aws iam put-role-policy `
    --role-name $RoleName `
    --policy-name "connect-nlu-router-menu-permissions" `
    --policy-document "file://$root\infra\permissions-policy.json"

Start-Sleep -Seconds 10  # IAM propagation

# 2. Lambda function.
& "$PSScriptRoot\package_lambda.ps1"
& $Aws lambda create-function `
    --function-name $FunctionName `
    --runtime python3.14 `
    --role "arn:aws:iam::${AccountId}:role/${RoleName}" `
    --handler connect_nlu_router_menu.handler.lambda_handler `
    --zip-file "fileb://$root\lambda-package.zip" `
    --timeout 30 `
    --memory-size 256 `
    --architectures x86_64 `
    --environment "Variables={NOVA_MODEL_ID=amazon.nova-micro-v1:0}" `
    --region $Region

& $Aws lambda wait function-active-v2 --function-name $FunctionName --region $Region

Write-Host "`nProvisioned $FunctionName."
