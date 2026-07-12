import hmac
import json
import logging

from pydantic import ValidationError

from telegram_inbound_adapter.models import TelegramUpdate

logger = logging.getLogger(__name__)

SECRET_TOKEN_HEADER = "x-telegram-bot-api-secret-token"


def verify_secret_token(headers: dict[str, str], expected_secret: str) -> bool:
    normalized = {k.lower(): v for k, v in headers.items()}
    received = normalized.get(SECRET_TOKEN_HEADER, "")
    return hmac.compare_digest(received, expected_secret)


def parse_telegram_update(body: str) -> TelegramUpdate | None:
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        logger.warning("telegram_update_invalid_json")
        return None

    try:
        return TelegramUpdate.model_validate(payload)
    except ValidationError:
        logger.warning("telegram_update_invalid_schema")
        return None
