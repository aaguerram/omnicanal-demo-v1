import httpx

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramClient:
    def __init__(self, bot_token: str, http_client: httpx.Client | None = None) -> None:
        self._base_url = f"{TELEGRAM_API_BASE}/bot{bot_token}"
        self._http = http_client or httpx.Client(timeout=5.0)

    def send_message(self, chat_id: int, text: str) -> None:
        response = self._http.post(
            f"{self._base_url}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
        response.raise_for_status()
