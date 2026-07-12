# Builds lambda-package.zip with Linux/x86_64 wheels for the Lambda python3.14 runtime.
# Run from the project root: .\scripts\package_lambda.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
New-Item -ItemType Directory -Path "build" | Out-Null

& ".\.venv\Scripts\python.exe" -m pip install `
    --platform manylinux2014_x86_64 `
    --target build `
    --implementation cp `
    --python-version 3.14 `
    --only-binary=:all: `
    --upgrade `
    -r requirements-lambda.txt

Copy-Item -Path "src\telegram_outbound_adapter" -Destination "build" -Recurse
Get-ChildItem -Path "build" -Filter "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force

if (Test-Path "lambda-package.zip") { Remove-Item "lambda-package.zip" -Force }
Compress-Archive -Path "build\*" -DestinationPath "lambda-package.zip" -CompressionLevel Optimal

Write-Host "Built lambda-package.zip ($([math]::Round((Get-Item 'lambda-package.zip').Length / 1MB, 2)) MB)"
