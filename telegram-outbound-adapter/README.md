# telegram-outbound-adapter

Lambda adapter that relays Amazon Connect real-time chat streaming events
(agent replies, and automated flow prompts like a menu) back to Telegram.

Sibling project to [`../telegram-inbound-adapter`](../telegram-inbound-adapter),
which handles the other direction (Telegram → Amazon Connect) and owns the
`ConversationSessions` DynamoDB table, the Secrets Manager secret, and the
Amazon Connect queues/flows. This project only reads/updates that table and
sends Telegram messages — it never talks to the Connect/Connect Participant
APIs directly.

## Flow

```
Amazon Connect (agent message or flow prompt)
    1. Contact streaming publishes the event to an SNS topic
    2. SNS invokes this Lambda (telegram-outbound-adapter)
    3. Look up the Telegram chat_id via DynamoDB (pk = "contact#<ContactId>")
    4. Skip CUSTOMER-authored messages (would echo the user's own text back)
    5. On a "chat.ended" event: mark the session ENDED in DynamoDB
    6. Otherwise: send the message text to Telegram (sendMessage)
```

## Architecture

```
handler.py             thin Lambda entrypoint: wiring + delegation
repositories/           DynamoDB session repository (read/update only)
clients/                Telegram Bot API client
```

## Requirements

- Python 3.14
- The `ConversationSessions` DynamoDB table and `telegram-inbound-adapter/telegram-bot`
  Secrets Manager secret from `../telegram-inbound-adapter` must already exist.

## Local setup

```bash
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env   # fill in values for local testing
pytest
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `DYNAMODB_TABLE_NAME` | Session table (default `ConversationSessions`, shared with telegram-inbound-adapter) |
| `TELEGRAM_SECRET_NAME` | Secrets Manager secret holding `bot_token` (same secret telegram-inbound-adapter uses) |
| `TELEGRAM_BOT_TOKEN` | Local-only override; in Lambda this comes from Secrets Manager instead |

## Deployment

- `scripts/provision.ps1` — one-time setup: SNS topic (with the resource
  policy that lets `connect.amazonaws.com` publish to it), IAM role, Lambda
  function, and SNS→Lambda subscription.
- `scripts/package_lambda.ps1` — builds `lambda-package.zip` with Linux/x86_64
  wheels for the Lambda `python3.14` runtime (pydantic-core is a compiled
  dependency, so this uses `pip install --platform manylinux2014_x86_64
  --only-binary=:all:` to cross-download the right wheels from Windows).
- `scripts/deploy.ps1` — rebuilds and pushes new code to the existing function.

### Currently deployed (account 042278586355, us-east-1)

| Resource | Value |
| --- | --- |
| Lambda function | `telegram-outbound-adapter` (python3.14) |
| SNS topic | `telegram-inbound-adapter-chat-events` |
| DynamoDB table | `ConversationSessions` (shared, owned by telegram-inbound-adapter) |
| Secrets Manager | `telegram-inbound-adapter/telegram-bot` (shared, owned by telegram-inbound-adapter) |
| Amazon Connect instance | `intuito-connect-omni` (`1029ff15-e0f3-4b9c-bab2-377c17509765`) |

To redeploy code changes: `.\scripts\deploy.ps1`.

**IAM policy note**: the SNS topic's access policy must use `ArnEquals` on
the bare Connect instance ARN (`arn:aws:connect:<region>:<account>:instance/<id>`),
**not** `ArnLike` with a `/*` suffix — the latter doesn't match Connect's
actual `SourceArn` for this publish and silently denies it (no CloudWatch
metric, no error anywhere — the topic just never receives anything). See
`scripts/provision.ps1` for the correct policy.

## Running locally

This Lambda is SNS-triggered, not HTTP-triggered, so there's no server to
run. `scripts/run_local.py` instead loads a JSON file shaped like the SNS
event Lambda receives and invokes the handler directly against your real AWS
credentials (real DynamoDB table, real Telegram API):

```bash
copy scripts\sample_sns_event.json scripts\my_event.json
# edit my_event.json: set ContactId to a real, currently-active contact
# (check the ConversationSessions table for a "contact#<id>" item)
.venv\Scripts\python.exe scripts\run_local.py scripts\my_event.json
```

To also save that output to a timestamped file (`logs\<yyyy-MM-dd_HH-mm-ss>.txt`),
use `scripts\run_local_logged.ps1` instead:
```powershell
.\scripts\run_local_logged.ps1 scripts\my_event.json
```
`logs/` is gitignored.

### Local observability (traces/metrics/logs in console)

`run_local.py` wires up `telemetry.py` before importing the handler, so every
local run prints OpenTelemetry spans (DynamoDB and Telegram httpx calls),
periodic metrics, and structured logs — all correlated by a single `trace_id`
per invocation, plus your existing `logger.info`/`.exception` calls. This is
dev-only: `handler.py` never imports `telemetry.py`, so the deployed Lambda
is unaffected and just uses plain `logging.basicConfig` console output
(visible in CloudWatch Logs).

Request/response payloads are captured on spans too — anything that looks
like a token or secret is redacted before it's printed or written to a log
file (same redaction logic as telegram-inbound-adapter's `telemetry.py`).
