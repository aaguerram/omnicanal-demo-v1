# One-time provisioning of the AWS resources behind agentic-skincare-backend.
# Idempotent-ish: safe to re-run individual sections, but create-* calls will
# fail loudly if the resource already exists (that's intentional, so you
# don't silently overwrite a live secret or table).
#
# Prereq: scripts/create_gcp_service_account.ps1 already ran and left a JSON
# key file on disk -- pass its path as $GcpKeyFile below. Also needs Docker
# Desktop running locally (this Lambda deploys as a container image, not a
# zip -- see Dockerfile's top comment for why).
#
# Run from the project root: .\scripts\provision.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$Aws = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
$Region = "us-east-1"
$AccountId = "042278586355"
$ConnectInstanceId = "1029ff15-e0f3-4b9c-bab2-377c17509765"
$FunctionName = "agentic-skincare-backend"
$RoleName = "agentic-skincare-backend-lambda-role"
$TableName = "SkincareAgentSessions"
$SecretName = "agentic-skincare-backend/gcp-service-account"
$GoogleCloudProject = "skincare-ai-commerce"
$ImageUri = "${AccountId}.dkr.ecr.${Region}.amazonaws.com/${FunctionName}:latest"
$GcpKeyFile = $env:GCP_SERVICE_ACCOUNT_KEY_FILE   # set this in your shell before running -- see scripts/create_gcp_service_account.ps1

if (-not $GcpKeyFile -or -not (Test-Path $GcpKeyFile)) {
    throw "Set `$env:GCP_SERVICE_ACCOUNT_KEY_FILE to the path of the service account JSON key before running (see scripts/create_gcp_service_account.ps1)."
}

# 1. DynamoDB table
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

# 3. IAM role + inline policy (see infra/trust-policy.json and infra/permissions-policy.json)
& $Aws iam create-role `
    --role-name $RoleName `
    --assume-role-policy-document "file://$root\infra\trust-policy.json" `
    --description "Execution role for agentic-skincare-backend Lambda"

& $Aws iam put-role-policy `
    --role-name $RoleName `
    --policy-name "agentic-skincare-backend-permissions" `
    --policy-document "file://$root\infra\permissions-policy.json"

Start-Sleep -Seconds 10  # IAM propagation

# 4. ECR repository + container image (see Dockerfile and package_lambda.ps1
# for why this is an image, not a zip)
& $Aws ecr create-repository --repository-name $FunctionName --region $Region
& "$PSScriptRoot\package_lambda.ps1"

# 5. Lambda function. 2048 MB / 60s: at the default 512 MB / 20s the cold
# start alone (importing langchain/langgraph/google-cloud-firestore) blew
# past Lambda's separate, non-configurable 10s INIT-phase limit and the
# function timed out before ever reaching the handler -- Lambda allocates
# CPU proportional to memory, so more memory cuts cold-start import time,
# and the extra timeout budget covers the couple of sequential Bedrock calls
# (router + feature node + estado_turno) a cold invoke makes.
& $Aws lambda create-function `
    --function-name $FunctionName `
    --package-type Image `
    --code "ImageUri=$ImageUri" `
    --role "arn:aws:iam::${AccountId}:role/${RoleName}" `
    --timeout 60 `
    --memory-size 2048 `
    --architectures x86_64 `
    --environment "Variables={DYNAMODB_TABLE_NAME=$TableName,GOOGLE_CLOUD_PROJECT=$GoogleCloudProject,GCP_SECRET_NAME=$SecretName,NOVA_MODEL_ID=amazon.nova-micro-v1:0}" `
    --region $Region

& $Aws lambda wait function-active-v2 --function-name $FunctionName --region $Region

# 6. Let Amazon Connect invoke this Lambda directly from a contact flow
# (InvokeLambdaFunction block in F_IA_Ventas / F_IA_Ventas_Loop -- see
# telegram-inbound-adapter/scripts/provision_connect_flows.py). Mirrors the
# manual step context.md documents for connect-nlu-router-menu, baked in here
# instead of left as a follow-up.
& $Aws lambda add-permission `
    --function-name $FunctionName `
    --statement-id "connect-invoke" `
    --action lambda:InvokeFunction `
    --principal connect.amazonaws.com `
    --source-account $AccountId `
    --region $Region

& $Aws connect associate-lambda-function `
    --instance-id $ConnectInstanceId `
    --function-arn "arn:aws:lambda:${Region}:${AccountId}:function:${FunctionName}" `
    --region $Region

Write-Host "`nProvisioned $FunctionName. Next steps:"
Write-Host "  1. Run telegram-inbound-adapter/scripts/provision_connect_flows.py --update"
Write-Host "     to point F_IA_Ventas at this Lambda (SKINCARE_LAMBDA_ARN)."
