# Rebuilds the Lambda package and pushes new code to the existing
# connect-nlu-router-menu function. Use scripts/provision.ps1 for the
# one-time creation of the surrounding AWS resources.
#
# Run from the project root: .\scripts\deploy.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$Aws = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
$Region = "us-east-1"
$FunctionName = "connect-nlu-router-menu"

& "$PSScriptRoot\package_lambda.ps1"

& $Aws lambda update-function-code `
    --function-name $FunctionName `
    --zip-file "fileb://$root\lambda-package.zip" `
    --region $Region

& $Aws lambda wait function-updated-v2 --function-name $FunctionName --region $Region

Write-Host "Deployed $FunctionName."
