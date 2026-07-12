# One-time provisioning of the AWS resources behind telegram-outbound-adapter:
# an SNS topic that Amazon Connect real-time chat streaming publishes to, and
# the Lambda function (subscribed to that topic) that relays messages to
# Telegram.
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
$ConnectInstanceId = "1029ff15-e0f3-4b9c-bab2-377c17509765"
$FunctionName = "telegram-outbound-adapter"
$RoleName = "telegram-outbound-adapter-lambda-role"
$TableName = "ConversationSessions"
$SecretName = "telegram-inbound-adapter/telegram-bot"
$TopicName = "telegram-inbound-adapter-chat-events"

# 1. SNS topic that Amazon Connect real-time contact streaming publishes to.
$topic = & $Aws sns create-topic --name $TopicName --region $Region | ConvertFrom-Json
$topicArn = $topic.TopicArn
Write-Host "SNS topic: $topicArn"

$topicPolicy = @{
    Version   = "2012-10-17"
    Statement = @(
        @{
            Sid       = "AllowConnectPublish"
            Effect    = "Allow"
            Principal = @{ Service = "connect.amazonaws.com" }
            Action    = "SNS:Publish"
            Resource  = $topicArn
            Condition = @{
                StringEquals = @{ "aws:SourceAccount" = $AccountId }
                # Must be ArnEquals against the bare instance ARN, matching
                # AWS's documented example exactly -- ArnLike with a "/*"
                # suffix does NOT match (Connect's SourceArn for this publish
                # is the instance ARN itself, nothing after it), which
                # silently denies the publish: no CloudWatch metric, no
                # visible error anywhere, the SNS topic just never receives
                # anything. This cost real debugging time -- don't "fix" it
                # back to ArnLike.
                ArnEquals    = @{ "aws:SourceArn" = "arn:aws:connect:${Region}:${AccountId}:instance/${ConnectInstanceId}" }
            }
        }
    )
} | ConvertTo-Json -Depth 6 -Compress

$topicPolicyFile = "$env:TEMP\telegram-outbound-adapter-topic-policy.json"
Set-Content -Path $topicPolicyFile -Value $topicPolicy -Encoding ascii -NoNewline
& $Aws sns set-topic-attributes `
    --topic-arn $topicArn `
    --attribute-name Policy `
    --attribute-value "file://$topicPolicyFile" `
    --region $Region

# 2. IAM role + inline policy (see infra/trust-policy.json and infra/permissions-policy.json).
& $Aws iam create-role `
    --role-name $RoleName `
    --assume-role-policy-document "file://$root\infra\trust-policy.json" `
    --description "Execution role for telegram-outbound-adapter Lambda"

& $Aws iam put-role-policy `
    --role-name $RoleName `
    --policy-name "telegram-outbound-adapter-permissions" `
    --policy-document "file://$root\infra\permissions-policy.json"

Start-Sleep -Seconds 10  # IAM propagation

# 3. Lambda function.
& "$PSScriptRoot\package_lambda.ps1"
& $Aws lambda create-function `
    --function-name $FunctionName `
    --runtime python3.14 `
    --role "arn:aws:iam::${AccountId}:role/${RoleName}" `
    --handler telegram_outbound_adapter.handler.lambda_handler `
    --zip-file "fileb://$root\lambda-package.zip" `
    --timeout 15 `
    --memory-size 256 `
    --architectures x86_64 `
    --environment "Variables={DYNAMODB_TABLE_NAME=$TableName,TELEGRAM_SECRET_NAME=$SecretName}" `
    --region $Region

& $Aws lambda wait function-active-v2 --function-name $FunctionName --region $Region

# 4. SNS -> Lambda subscription + invoke permission.
& $Aws lambda add-permission `
    --function-name $FunctionName `
    --statement-id "sns-invoke" `
    --action lambda:InvokeFunction `
    --principal sns.amazonaws.com `
    --source-arn $topicArn `
    --region $Region

$functionArn = "arn:aws:lambda:${Region}:${AccountId}:function:${FunctionName}"
& $Aws sns subscribe `
    --topic-arn $topicArn `
    --protocol lambda `
    --notification-endpoint $functionArn `
    --region $Region

Write-Host "`nProvisioned. Set this in telegram-inbound-adapter's environment (and .env)"
Write-Host "as CHAT_EVENTS_TOPIC_ARN so it tells Connect where to stream to:"
Write-Host "  $topicArn"
