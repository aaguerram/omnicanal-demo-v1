# Builds and deploys entrypoints/agentcore_app.py to Amazon Bedrock AgentCore
# Runtime using the bedrock-agentcore-starter-toolkit (AWS's CLI for this --
# note as of this writing the toolkit itself prints a deprecation notice
# pointing at a newer `@aws/agentcore` npm CLI, but `deploy`/`configure`
# still work and this keeps the deploy path in Python, consistent with the
# rest of this repo; suppressed below with AGENTCORE_SUPPRESS_RECOMMENDATION).
# `agentcore deploy` with no flags generates the Dockerfile, uploads the
# source and builds an ARM64 image remotely via AWS CodeBuild, then calls
# create-agent-runtime -- there is no local `docker build`/`docker push`
# anywhere in this script, on purpose (see ../context.md for why).
#
# Prereq: scripts/provision_agentcore.ps1 already ran (DynamoDB table,
# secret, IAM execution role).
#
# Run from the project root: .\scripts\deploy_agentcore.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$Region = "us-east-1"
$AccountId = "042278586355"
$AgentName = "agentic_skincare_backend"   # AgentCore runtime names: letters/digits/underscores only, no hyphens
$RoleArn = "arn:aws:iam::${AccountId}:role/agentic-skincare-backend-agentcore-role"

# Este entorno de Windows tira UnicodeEncodeError al renderizar los emojis
# del banner de deprecacion/progreso del toolkit sobre la consola cp1252 por
# default -- forzar UTF-8 lo evita. AGENTCORE_SUPPRESS_RECOMMENDATION silencia
# el aviso de deprecacion (ya leido y evaluado, ver comentario de arriba).
$env:AGENTCORE_SUPPRESS_RECOMMENDATION = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

python -m pip install --upgrade bedrock-agentcore bedrock-agentcore-starter-toolkit
if ($LASTEXITCODE -ne 0) { throw "pip install bedrock-agentcore-starter-toolkit failed with exit code $LASTEXITCODE" }

# Las instalaciones --user de Python en Windows no agregan siempre Scripts
# al PATH de la sesion actual. Resolver el ejecutable de forma determinista
# evita que el deploy falle justo despues de instalarlo correctamente.
$PythonUserBase = python -m site --user-base
if ($LASTEXITCODE -ne 0) { throw "python -m site --user-base failed with exit code $LASTEXITCODE" }
$AgentCoreCli = Join-Path $PythonUserBase "Python312\Scripts\agentcore.exe"
if (-not (Test-Path -LiteralPath $AgentCoreCli)) {
    # En algunas instalaciones --user-base ya incluye PythonXY.
    $AgentCoreCli = Join-Path $PythonUserBase "Scripts\agentcore.exe"
}
if (-not (Test-Path -LiteralPath $AgentCoreCli)) {
    throw "agentcore.exe not found under Python user base: $PythonUserBase"
}

# --deployment-type container: nuestro stack (langchain/langgraph/
# google-cloud-firestore) ya se sabe que da ~459 MB descomprimido (ver
# Historial en ../context.md), muy por encima de cualquier limite de tipo
# zip/direct_code_deploy -- container es el unico tipo probado que soporta
# ese peso (hasta 10 GB).
& $AgentCoreCli configure `
    --entrypoint entrypoints/agentcore_app.py `
    --name $AgentName `
    --execution-role $RoleArn `
    --requirements-file requirements-agentcore.txt `
    --deployment-type container `
    --region $Region `
    --non-interactive
if ($LASTEXITCODE -ne 0) { throw "agentcore configure failed with exit code $LASTEXITCODE" }

# Sin --local ni --local-build: build remoto en CodeBuild, cero Docker en
# esta maquina (ver `agentcore deploy --help`).
& $AgentCoreCli deploy
if ($LASTEXITCODE -ne 0) { throw "agentcore deploy failed with exit code $LASTEXITCODE" }

Write-Host "`nDeployed. Run 'agentcore status' to get the agent runtime ARN, then set"
Write-Host "it as AGENT_RUNTIME_ARN for agentic-skincare-adapter (see its provision.ps1)."
