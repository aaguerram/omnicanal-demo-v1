# Rebuilds the container image and pushes new code to the existing
# agentic-skincare-backend function. Use scripts/provision.ps1 for the
# one-time creation of the surrounding AWS resources.
#
# Run from the project root: .\scripts\deploy.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$Aws = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
$Region = "us-east-1"
$AccountId = "042278586355"
$FunctionName = "agentic-skincare-backend"
$ImageUri = "${AccountId}.dkr.ecr.${Region}.amazonaws.com/${FunctionName}:latest"

& "$PSScriptRoot\package_lambda.ps1"

& $Aws lambda update-function-code `
    --function-name $FunctionName `
    --image-uri $ImageUri `
    --region $Region

& $Aws lambda wait function-updated-v2 --function-name $FunctionName --region $Region

Write-Host "Deployed $FunctionName."
