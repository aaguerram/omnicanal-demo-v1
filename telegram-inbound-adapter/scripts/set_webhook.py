"""Points the Telegram bot's webhook at a given base URL (local tunnel or the
deployed API Gateway) using the token/secret from .env.

Usage:
    .venv\\Scripts\\python.exe scripts\\set_webhook.py
        Auto-detects the latest trycloudflare.com URL from the
        `telegram-inbound-adapter-tunnel` Docker container's logs and uses it.
        Use this after the Docker tunnel reconnects with a new URL.

    .venv\\Scripts\\python.exe scripts\\set_webhook.py https://<tunnel>.trycloudflare.com
    .venv\\Scripts\\python.exe scripts\\set_webhook.py https://gcaqi51xuj.execute-api.us-east-1.amazonaws.com
        Points at an explicit URL (native cloudflared, or the deployed Lambda).
"""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import httpx

from telegram_inbound_adapter.settings import get_settings

TUNNEL_CONTAINER_NAME = "telegram-inbound-adapter-tunnel"
TUNNEL_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def latest_tunnel_url_from_docker_logs() -> str:
    try:
        result = subprocess.run(
            ["docker", "logs", TUNNEL_CONTAINER_NAME],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError(
            f"Could not read logs for container '{TUNNEL_CONTAINER_NAME}'. "
            "Is `docker compose up` running in infra/cloudflared, and is Docker on PATH?"
        ) from exc

    matches = TUNNEL_URL_PATTERN.findall(result.stdout + result.stderr)
    if not matches:
        raise RuntimeError(
            f"No trycloudflare.com URL found in logs for container '{TUNNEL_CONTAINER_NAME}' yet."
        )
    return matches[-1]


def main() -> None:
    if len(sys.argv) > 2:
        print(__doc__)
        raise SystemExit(1)

    if len(sys.argv) == 2:
        base_url = sys.argv[1].rstrip("/")
    else:
        base_url = latest_tunnel_url_from_docker_logs()
        print(f"Auto-detected tunnel URL from Docker logs: {base_url}")

    settings = get_settings()

    response = httpx.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
        json={
            "url": f"{base_url}/telegram/webhook",
            "secret_token": settings.telegram_webhook_secret,
            "allowed_updates": ["message"],
            "drop_pending_updates": True,
        },
    )
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
