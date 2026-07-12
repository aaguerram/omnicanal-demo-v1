# Builds and pushes the container image for the agentic-skincare-backend
# Lambda to ECR. A zip-based package (the original approach here) came out
# to ~459 MB unzipped -- over Lambda's 250 MB zip limit, mostly
# langchain-community's transitive weight pulled in by
# langchain-google-firestore (Vertex AI/google-cloud-aiplatform is gone now
# that chat/embeddings run on Bedrock, but the image still comfortably clears
# the zip limit). Container images go up to 10 GB, so this avoids fragile
# pruning of "unused" transitive packages.
# Run from the project root: .\scripts\package_lambda.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$Aws = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
$Region = "us-east-1"
$AccountId = "042278586355"
$RepoName = "agentic-skincare-backend"
$ImageUri = "${AccountId}.dkr.ecr.${Region}.amazonaws.com/${RepoName}:latest"

& $Aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin "${AccountId}.dkr.ecr.${Region}.amazonaws.com"
if ($LASTEXITCODE -ne 0) { throw "docker login to ECR failed with exit code $LASTEXITCODE" }

# --provenance=false: buildx's default output includes an OCI-format
# manifest/attestation that Lambda's CreateFunction rejects ("image manifest,
# config or layer media type ... is not supported") -- this forces the
# older Docker v2 schema 2 manifest Lambda actually accepts.
docker build --platform linux/amd64 --provenance=false -f Dockerfile.container-lambda-legacy -t "${RepoName}:latest" .
if ($LASTEXITCODE -ne 0) { throw "docker build failed with exit code $LASTEXITCODE" }

docker tag "${RepoName}:latest" $ImageUri
docker push $ImageUri
if ($LASTEXITCODE -ne 0) { throw "docker push failed with exit code $LASTEXITCODE" }

Write-Host "Pushed $ImageUri"
