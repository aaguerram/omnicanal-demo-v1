# telegram-inbound-adapter

Lambda adapter that receives Telegram Bot webhook updates and bridges them into
Amazon Connect chat sessions.

Handles Telegram → Amazon Connect only. The other direction (agent replies
and flow prompts → Telegram) is a separate sibling project,
[`../telegram-outbound-adapter`](../telegram-outbound-adapter) — it reads the
same `ConversationSessions` table and `telegram-inbound-adapter/telegram-bot`
secret this project owns, but is deployed and versioned independently.

## Flow

```
Telegram → API Gateway (POST /telegram/webhook) → Lambda (telegram-inbound-adapter)
    1. Validar secret token (X-Telegram-Bot-Api-Secret-Token)
    2. Buscar sesión en DynamoDB (ConversationSessions, pk = telegram#<chat_id>)
    3. Si existe: SendMessage a Amazon Connect (Connect Participant Service)
    4. Si no existe (o el SendMessage de arriba fallo por sesion stale):
       StartChatContact (el texto del usuario viaja SOLO como el atributo de
       contacto `initialMessage` -- deliberadamente NUNCA como InitialMessage
       ni SendMessage, ver gotcha #12 en ../context.md)
       -> StartContactStreaming -> CreateParticipantConnection
       (in that order -- streaming must be active before the flow starts producing
       messages, and CreateParticipantConnection needs ConnectParticipant=true for
       streaming to actually deliver events to the SNS topic). See ../context.md
       (gotchas #7 y #12) para el historial completo: primero una SendMessage
       separada competia con el GetParticipantInput de F_Menu_Router (gotcha #7);
       el intento de arreglarlo con InitialMessage dejaba igual un mensaje sin
       consumir en el canal que rompia el primer GetParticipantInput que el
       contacto SI llegaba a usar, el de F_Menu_Reintento (gotcha #12).
    5. Responder 200 a Telegram
```

Replies flowing back the other way (agent messages, flow prompts) go through
Amazon Connect's real-time chat streaming → SNS → `telegram-outbound-adapter`,
not through this project.

## Architecture

```
handler.py            thin Lambda entrypoint: wiring + delegation
validation.py          secret-token check + Telegram payload parsing
services/chat_service  business logic / orchestration
repositories/          DynamoDB session repository
clients/                Amazon Connect + Telegram Bot API clients
```

## Requirements

- Python 3.14
- AWS account with an Amazon Connect instance
- A Telegram bot token (from @BotFather)

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
| `CONNECT_INSTANCE_ID` | Amazon Connect instance ID |
| `CONNECT_CONTACT_FLOW_ID` | Contact flow used for `StartChatContact` (`F_Entrada_Omnicanal`) |
| `CHAT_EVENTS_TOPIC_ARN` | SNS topic passed to `StartContactStreaming`; consumed by `telegram-outbound-adapter` |
| `DYNAMODB_TABLE_NAME` | Session table (default `ConversationSessions`) |
| `TELEGRAM_SECRET_NAME` | Secrets Manager secret holding `bot_token` + `webhook_secret` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_WEBHOOK_SECRET` | Local-only overrides; in Lambda these come from Secrets Manager instead |

In Lambda, the bot token and webhook secret are fetched once per cold start from
Secrets Manager (`TELEGRAM_SECRET_NAME`) — never stored as plaintext Lambda
environment variables.

## Deployment

- `scripts/provision.ps1` — one-time setup: DynamoDB table, Secrets Manager
  secret, IAM role, Lambda function, API Gateway route, and Telegram webhook
  registration. Set `$env:TELEGRAM_BOT_TOKEN` before running.
- `scripts/provision_queues_routing.ps1` — one-time setup of the 3 intent-based
  Amazon Connect queues (`Q_Soporte`, `Q_Ventas`, `Q_Cobranza`) and the shared
  routing profile (`RP_Asesores_Mensajeria_Omnicanal`). There is no
  "unrecognized input" queue -- unmatched input falls back to `F_Menu_Reintento`
  (see below), and technical failures fall back to `Q_Soporte`. A 4th queue,
  `Q_Atencion`, existed as a catch-all and was deleted 2026-07-11 (see
  `../context.md` Historial) -- it was defeating the whole point of
  `F_Menu_Reintento` by matching any greeting/ambiguous message.
- `scripts/provision_connect_flows.py` — one-time setup of the 8 contact flows
  (`F_Entrada_Omnicanal`, `F_Menu_Router`, `F_Menu_Reintento`,
  `F_IA_Soporte/Ventas/Cobranza` stubs, `F_Handoff_Humano`, `F_Espera_Cola`).
  Run after `provision_queues_routing.ps1` — it looks up the queue IDs by
  name. Run with `.venv\Scripts\python.exe scripts\provision_connect_flows.py`.
  To push the current `F_IA_Ventas` services-message text (and
  `F_Handoff_Humano`/`F_Menu_Router`/`F_Menu_Reintento`/`F_Entrada_Omnicanal`)
  to already-deployed flows without recreating them, run
  `... scripts\provision_connect_flows.py --update`.
  `F_Menu_Reintento` is the flow the NLU classifier falls back to when it
  can't match a valid intent -- it explains what it can help with and
  re-classifies, transferring to itself (no cap, no fallback to a human
  queue at this point) until a valid intent is detected. See `../context.md`
  (gotcha #7 and the Historial entries) for why that loop is a
  `TransferToFlow` between two flows rather than a back-edge inside one --
  the latter caused a real runaway-message incident previously. `F_Menu_Router`
  itself never prompts or waits for input -- it classifies
  `$.Attributes.initialMessage` (seeded by `chat_service.py` at
  `StartChatContact` time, as a contact attribute ONLY -- deliberately never
  as an actual chat message, see gotcha #12) directly, since the customer
  already said something to trigger the contact; see the same context.md
  entries for the race condition this replaced (a separate `SendMessage`
  call used to compete with `F_Menu_Router`'s own `GetParticipantInput`).
- `scripts/package_lambda.ps1` — builds `lambda-package.zip` with Linux/x86_64
  wheels for the Lambda `python3.14` runtime (pydantic-core is a compiled
  dependency, so this uses `pip install --platform manylinux2014_x86_64
  --only-binary=:all:` to cross-download the right wheels from Windows).
- `scripts/deploy.ps1` — rebuilds and pushes new code to an existing function.

### Currently deployed (account 042278586355, us-east-1)

| Resource | Value |
| --- | --- |
| Lambda function | `telegram-inbound-adapter` (python3.14) |
| API Gateway endpoint | `https://gcaqi51xuj.execute-api.us-east-1.amazonaws.com/telegram/webhook` |
| DynamoDB table | `ConversationSessions` (PK `pk` = `telegram#<chat_id>` or `contact#<contactId>`, TTL on `ttl`) |
| Secrets Manager | `telegram-inbound-adapter/telegram-bot` (`bot_token`, `webhook_secret`) |
| Amazon Connect instance | `intuito-connect-omni` (`1029ff15-e0f3-4b9c-bab2-377c17509765`) |
| Contact flow | `F_Entrada_Omnicanal` — entry point; routes to `F_Menu_Router` on the first message, or straight back to the active `F_IA_*` flow on subsequent ones |
| Queues / routing profile | `Q_Soporte`, `Q_Ventas`, `Q_Cobranza` / `RP_Asesores_Mensajeria_Omnicanal` |
| SNS topic (chat streaming) | `telegram-inbound-adapter-chat-events` — consumed by `telegram-outbound-adapter` |
| Telegram bot | `@intuito_soporte_test_v1_bot` |

To redeploy code changes: `.\scripts\deploy.ps1`.

## Running the chat locally

This lets you iterate without redeploying to Lambda, using your real AWS
credentials against the real DynamoDB table and Connect instance. Two ways
to get the tunnel: a native `cloudflared` binary, or `cloudflared` in Docker
(`infra/cloudflared/`) — pick whichever you have installed.

### Option A — native cloudflared

1. Make sure `.env` exists (see Local setup above) with
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_SECRET` filled in.
2. Start the local server (wraps `lambda_handler` behind plain HTTP):
   ```bash
   .venv\Scripts\python.exe scripts\run_local.py 8000
   ```
3. In another terminal, start a tunnel so Telegram can reach your machine:
   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```
   Copy the `https://<random>.trycloudflare.com` URL it prints.
4. Point the bot's webhook at the tunnel:
   ```bash
   .venv\Scripts\python.exe scripts\set_webhook.py https://<random>.trycloudflare.com
   ```
5. Message `@intuito_soporte_test_v1_bot` on Telegram — updates now flow to
   your local process, logs print to the terminal running `run_local.py`.
6. **When done**, point the webhook back at the deployed Lambda so production
   traffic isn't silently dropped:
   ```bash
   .venv\Scripts\python.exe scripts\set_webhook.py https://gcaqi51xuj.execute-api.us-east-1.amazonaws.com
   ```

### Option B — cloudflared in Docker

Same idea, but the tunnel runs in a container instead of a local binary. Uses
`infra/cloudflared/docker-compose.yml`, which points at
`http://host.docker.internal:${LOCAL_PORT:-8000}` — the port is configurable.

1. Make sure `.env` exists (see Local setup above) with
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_SECRET` filled in.
2. Start the local server on the host (not in Docker):
   ```bash
   .venv\Scripts\python.exe scripts\run_local.py 8000
   ```
3. In another terminal, start the tunnel container:
   ```bash
   cd infra\cloudflared
   docker compose up
   ```
   To use a different port than 8000, either copy `.env.example` to `.env`
   in `infra\cloudflared` and set `LOCAL_PORT`, or pass it inline:
   ```bash
   LOCAL_PORT=9000 docker compose up -d
   ```
   (and start `run_local.py` on that same port in step 2).
4. Point the bot's webhook at the tunnel (from the project root) — no need
   to copy the URL by hand, this reads it straight from the container logs:
   ```bash
   .venv\Scripts\python.exe scripts\set_webhook.py
   ```
   (pass an explicit URL instead, e.g. `scripts\set_webhook.py https://<url>`,
   if you'd rather point at something else.)
5. Message `@intuito_soporte_test_v1_bot` on Telegram — updates now flow to
   your local process.
6. **When done**, stop the tunnel and point the webhook back at the deployed
   Lambda:
   ```bash
   cd infra\cloudflared
   docker compose down
   cd ..\..
   .venv\Scripts\python.exe scripts\set_webhook.py https://gcaqi51xuj.execute-api.us-east-1.amazonaws.com
   ```

### Local observability (traces/metrics/logs in console)

`run_local.py` wires up `telemetry.py` before importing the handler, so every
local run prints OpenTelemetry spans (DynamoDB, Connect, Telegram httpx
calls), periodic metrics, and structured logs — all correlated by a single
`trace_id` per webhook request (there's a root span for the incoming
`POST /telegram/webhook` itself, headers and body included, so every DynamoDB/
Connect/Telegram call made while handling it nests underneath it instead of
starting its own standalone trace), plus your existing `logger.info`/
`.exception` calls. This is dev-only: `handler.py` never imports
`telemetry.py`, so the deployed Lambda is unaffected.

Request/response payloads are captured on spans too (`aws.request.params`,
`aws.response.result`, `http.request.headers`, etc.) — anything that looks
like a token or secret (`connection_token`, `Authorization` header, the
Telegram bot token embedded in the URL, ...) is redacted before it's printed
or written to a log file.

To also save that output to a timestamped file (`logs\<yyyy-MM-dd_HH-mm-ss>.txt`)
instead of just scrolling past in the terminal, use
`scripts\run_local_logged.ps1` in place of `run_local.py` in step 2 above:
```powershell
.\scripts\run_local_logged.ps1 8000
```
`logs/` is gitignored.

### If the local console goes quiet mid-session

A quick tunnel can drop its connection and silently reconnect under a **new**
URL — Telegram keeps sending to the old (now dead) one and nothing shows up
locally. Check for this:
```bash
curl -s "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```
A `last_error_message` mentioning `530` is the tell. Fix it by re-running
(Docker option only, since it reads the container logs):
```bash
.venv\Scripts\python.exe scripts\set_webhook.py
```

A quick cloudflared tunnel (native or Docker) has no uptime guarantee and
its URL changes every run — fine for dev, not for anything long-lived. See
`infra/cloudflared/README.md` for more detail on the Docker option.
