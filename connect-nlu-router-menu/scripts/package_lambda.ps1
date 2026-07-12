# Builds lambda-package.zip with Linux/x86_64 wheels for the Lambda python3.14 runtime.
# Run from the project root: .\scripts\package_lambda.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
New-Item -ItemType Directory -Path "build" | Out-Null

# Varios --platform: numpy (dependencia transitiva via langchain-aws) solo
# publica wheels cp314 con tag manylinux_2_27/manylinux_2_28, mientras que
# pydantic-core (via pydantic) solo publica manylinux_2_17/manylinux2014 --
# pip con --platform explicito (cross-compilacion) hace match exacto de tag,
# no la cadena de compatibilidad descendente que usaria en una instalacion
# nativa, asi que un solo --platform deja sin resolver a alguno de los dos.
& ".\.venv\Scripts\python.exe" -m pip install `
    --platform manylinux2014_x86_64 `
    --platform manylinux_2_27_x86_64 `
    --platform manylinux_2_28_x86_64 `
    --target build `
    --implementation cp `
    --python-version 3.14 `
    --only-binary=:all: `
    --upgrade `
    -r requirements-lambda.txt
if ($LASTEXITCODE -ne 0) {
    # $ErrorActionPreference = "Stop" solo afecta errores de cmdlets de
    # PowerShell, no el exit code de un ejecutable nativo como pip -- sin
    # este chequeo explicito, un pip install fallido (p. ej.
    # ResolutionImpossible) se ignora en silencio y el script sigue
    # empaquetando un zip sin las dependencias instaladas.
    throw "pip install failed with exit code $LASTEXITCODE"
}

Copy-Item -Path "src\connect_nlu_router_menu" -Destination "build" -Recurse
Get-ChildItem -Path "build" -Filter "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force

if (Test-Path "lambda-package.zip") { Remove-Item "lambda-package.zip" -Force }
Compress-Archive -Path "build\*" -DestinationPath "lambda-package.zip" -CompressionLevel Optimal

Write-Host "Built lambda-package.zip ($([math]::Round((Get-Item 'lambda-package.zip').Length / 1MB, 2)) MB)"
