# cloudflared (Docker)

Runs a Cloudflare quick tunnel in a container that exposes the local dev
server (`scripts/run_local.py`, running directly on the host) to the
internet, so Telegram can reach it. No Cloudflare account needed.

The container reaches the host via `host.docker.internal`, so the local
server must be running on the host (not in a container) at the configured
port.

## Usage

1. Start the local server on the host, in the project root:
   ```bash
   .venv\Scripts\python.exe scripts\run_local.py 8000
   ```
2. (Optional) Copy `.env.example` to `.env` here and set `LOCAL_PORT` if
   you started the server on a different port:
   ```bash
   copy .env.example .env
   ```
3. Start the tunnel:
   ```bash
   docker compose up
   ```
   or with the port set inline instead of via `.env`:
   ```bash
   LOCAL_PORT=9000 docker compose up
   ```
4. Point Telegram's webhook at it (from the project root) — this reads the
   latest URL straight from the container logs, no copy-pasting needed:
   ```bash
   .venv\Scripts\python.exe ..\..\scripts\set_webhook.py
   ```

## Changing the port

Either edit `LOCAL_PORT` in `.env`, or pass it inline:
```bash
LOCAL_PORT=9000 docker compose up
```
Restart the container after changing it (`docker compose up` again — compose
recreates the container when the resolved command differs).

## Stopping

```bash
docker compose down
```

Remember to point the webhook back at the deployed Lambda afterward:
```bash
.venv\Scripts\python.exe ..\..\scripts\set_webhook.py https://gcaqi51xuj.execute-api.us-east-1.amazonaws.com
```

## If messages stop showing up locally

A quick tunnel has no uptime guarantee — if its connection drops mid-session,
`cloudflared` silently reconnects under a **new** random URL, but Telegram
keeps sending to the old (now dead) one. Check
`curl -s "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"` for a
`last_error_message` mentioning `530`, then re-run
`..\..\scripts\set_webhook.py` (no args) to re-detect and re-point at the
current URL.
