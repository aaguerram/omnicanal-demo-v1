# One-time provisioning of the AWS resources behind the Bedrock AgentCore
# Runtime deployment of agentic-skincare-backend -- everything EXCEPT the
# runtime itself (that's scripts/deploy_agentcore.ps1, which uses the
# bedrock-agentcore-starter-toolkit to build via CodeBuild and call
# create-agent-runtime -- no Docker involved anywhere in this path).
#
# Replaces the ECR/Lambda/Connect sections of the old scripts/provision.ps1
# (container-Lambda path, unused now but left in the repo) -- see
# ../context.md for why hosting moved to AgentCore Runtime.
#
# Prereq: scripts/create_gcp_service_account.ps1 already ran and left
# gcp-service-account-key.json at the project root (it has, as of this
# change -- reused as-is, not recreated).
#
# Idempotent-ish: safe to re-run individual sections, but create-* calls will
# fail loudly if the resource already exists (that's intentional, so you
# don't silently overwrite a live secret or table).
#
# Run from the project root: .\scripts\provision_agentcore.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$Aws = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
$Region = "us-east-1"
$AccountId = "042278586355"
$RoleName = "agentic-skincare-backend-agentcore-role"
$TableName = "SkincareAgentSessions"
$SecretName = "agentic-skincare-backend/gcp-service-account"
$GcpKeyFile = "$root\gcp-service-account-key.json"

if (-not (Test-Path $GcpKeyFile)) {
    throw "$GcpKeyFile not found -- run scripts/create_gcp_service_account.ps1 first."
}

# 1. DynamoDB table (session persistence, ver core/turn_service.py /
# repositories/session_repository.py -- sin cambios respecto al diseno
# original, AgentCore Runtime no reemplaza esta necesidad).
& $Aws dynamodb create-table `
    --table-name $TableName `
    --attribute-definitions AttributeName=pk,AttributeType=S `
    --key-schema AttributeName=pk,KeyType=HASH `
    --billing-mode PAY_PER_REQUEST `
    --region $Region `
    --tags Key=project,Value=agentic-skincare-backend

& $Aws dynamodb wait table-exists --table-name $TableName --region $Region
& $Aws dynamodb update-time-to-live `
    --table-name $TableName `
    --time-to-live-specification "Enabled=true,AttributeName=ttl" `
    --region $Region

# 2. Secrets Manager: GCP service account JSON key, as-is (already valid JSON)
& $Aws secretsmanager create-secret `
    --name $SecretName `
    --description "GCP service account (Firestore) for agentic-skincare-backend" `
    --secret-string "file://$GcpKeyFile" `
    --region $Region

# 3. IAM role + inline policy for the AgentCore Runtime execution role (see
# infra/agentcore-trust-policy.json and infra/agentcore-permissions-policy.json
# -- principal bedrock-agentcore.amazonaws.com, not lambda.amazonaws.com).
& $Aws iam create-role `
    --role-name $RoleName `
    --assume-role-policy-document "file://$root\infra\agentcore-trust-policy.json" `
    --description "Execution role for agentic-skincare-backend Bedrock AgentCore Runtime"

& $Aws iam put-role-policy `
    --role-name $RoleName `
    --policy-name "agentic-skincare-backend-agentcore-permissions" `
    --policy-document "file://$root\infra\agentcore-permissions-policy.json"

Start-Sleep -Seconds 10  # IAM propagation

Write-Host "`nProvisioned DynamoDB table, secret and IAM role for AgentCore Runtime."
Write-Host "Next: .\scripts\deploy_agentcore.ps1 (agentcore configure + launch)."
Write-Host "Role ARN: arn:aws:iam::${AccountId}:role/${RoleName}"
