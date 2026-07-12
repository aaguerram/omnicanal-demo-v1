# One-time provisioning of the AWS resources behind telegram-inbound-adapter.
# Idempotent-ish: safe to re-run individual sections, but create-* calls will
# fail loudly if the resource already exists (that's intentional, so you
# don't silently overwrite a live secret or table).
#
# Fill in the variables below for your account before running.
# Run from the project root: .\scripts\provision.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$Aws = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
$Region = "us-east-1"
$AccountId = "042278586355"
$ConnectInstanceId = "1029ff15-e0f3-4b9c-bab2-377c17509765"
$ConnectContactFlowId = "834e58ca-8c31-4a40-9697-8fc16722eaa6"   # "Sample inbound flow (first contact experience)"
$TelegramBotToken = $env:TELEGRAM_BOT_TOKEN                       # set this in your shell before running
$FunctionName = "telegram-inbound-adapter"
$RoleName = "telegram-inbound-adapter-lambda-role"
$TableName = "ConversationSessions"
$SecretName = "telegram-inbound-adapter/telegram-bot"
$ApiName = "telegram-inbound-adapter-api"

if (-not $TelegramBotToken) {
    throw "Set `$env:TELEGRAM_BOT_TOKEN before running this script."
}

# 1. DynamoDB table
& $Aws dynamodb create-table `
    --table-name $TableName `
    --attribute-definitions AttributeName=pk,AttributeType=S `
    --key-schema AttributeName=pk,KeyType=HASH `
    --billing-mode PAY_PER_REQUEST `
    --region $Region `
    --tags Key=project,Value=telegram-inbound-adapter

& $Aws dynamodb wait table-exists --table-name $TableName --region $Region
& $Aws dynamodb update-time-to-live `
    --table-name $TableName `
    --time-to-live-specification "Enabled=true,AttributeName=ttl" `
    --region $Region

# 2. Secrets Manager: bot token + a freshly generated webhook secret
$WebhookSecret = & ".\.venv\Scripts\python.exe" -c "import secrets; print(secrets.token_urlsafe(32).replace('-', 'x').replace('_', 'y'))"
$secretPayload = @{ bot_token = $TelegramBotToken; webhook_secret = $WebhookSecret } | ConvertTo-Json -Compress
$secretFile = New-TemporaryFile
Set-Content -Path $secretFile -Value $secretPayload -Encoding utf8 -NoNewline
& $Aws secretsmanager create-secret `
    --name $SecretName `
    --description "Telegram bot token + webhook secret for telegram-inbound-adapter" `
    --secret-string "file://$secretFile" `
    --region $Region
Remove-Item $secretFile

# 3. IAM role + inline policy (see infra/trust-policy.json and infra/permissions-policy.json)
& $Aws iam create-role `
    --role-name $RoleName `
    --assume-role-policy-document "file://$root\infra\trust-policy.json" `
    --description "Execution role for telegram-inbound-adapter Lambda"

& $Aws iam put-role-policy `
    --role-name $RoleName `
    --policy-name "telegram-inbound-adapter-permissions" `
    --policy-document "file://$root\infra\permissions-policy.json"

Start-Sleep -Seconds 10  # IAM propagation

# 4. Lambda function
& "$PSScriptRoot\package_lambda.ps1"
& $Aws lambda create-function `
    --function-name $FunctionName `
    --runtime python3.14 `
    --role "arn:aws:iam::${AccountId}:role/${RoleName}" `
    --handler telegram_inbound_adapter.handler.lambda_handler `
    --zip-file "fileb://$root\lambda-package.zip" `
    --timeout 15 `
    --memory-size 256 `
    --architectures x86_64 `
    --environment "Variables={DYNAMODB_TABLE_NAME=$TableName,CONNECT_INSTANCE_ID=$ConnectInstanceId,CONNECT_CONTACT_FLOW_ID=$ConnectContactFlowId,TELEGRAM_SECRET_NAME=$SecretName}" `
    --region $Region

& $Aws lambda wait function-active-v2 --function-name $FunctionName --region $Region

# 5. API Gateway HTTP API with a POST /telegram/webhook route
$api = & $Aws apigatewayv2 create-api `
    --name $ApiName `
    --protocol-type HTTP `
    --target "arn:aws:lambda:${Region}:${AccountId}:function:${FunctionName}" `
    --region $Region | ConvertFrom-Json

$routes = & $Aws apigatewayv2 get-routes --api-id $api.ApiId --region $Region | ConvertFrom-Json
$defaultRoute = $routes.Items | Where-Object { $_.RouteKey -eq '$default' }
$integrationId = $defaultRoute.Target -replace 'integrations/', ''

& $Aws apigatewayv2 create-route `
    --api-id $api.ApiId `
    --route-key "POST /telegram/webhook" `
    --target "integrations/$integrationId" `
    --region $Region

& $Aws apigatewayv2 delete-route --api-id $api.ApiId --route-id $defaultRoute.RouteId --region $Region

& $Aws lambda add-permission `
    --function-name $FunctionName `
    --statement-id "apigateway-invoke" `
    --action lambda:InvokeFunction `
    --principal apigateway.amazonaws.com `
    --source-arn "arn:aws:execute-api:${Region}:${AccountId}:$($api.ApiId)/*/*/telegram/webhook" `
    --region $Region

$webhookUrl = "$($api.ApiEndpoint)/telegram/webhook"

# 6. Register the webhook with Telegram
$body = @{
    url = $webhookUrl
    secret_token = $WebhookSecret
    allowed_updates = @("message")
    drop_pending_updates = $true
} | ConvertTo-Json -Compress

Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$TelegramBotToken/setWebhook" `
    -ContentType "application/json" -Body $body

Write-Host "Provisioned. Webhook URL: $webhookUrl"
