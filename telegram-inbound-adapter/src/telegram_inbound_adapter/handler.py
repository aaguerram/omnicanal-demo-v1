import json
import logging
from typing import Any

import boto3

from telegram_inbound_adapter import validation
from telegram_inbound_adapter.clients.connect_client import ConnectClient
from telegram_inbound_adapter.clients.telegram_client import TelegramClient
from telegram_inbound_adapter.repositories.session_repository import SessionRepository
from telegram_inbound_adapter.services.chat_service import ChatService
from telegram_inbound_adapter.settings import get_settings

logging.basicConfig(level=logging.INFO)
# basicConfig() is a no-op if the root logger already has handlers -- and the
# Lambda Python runtime pre-attaches one before our code ever runs, so
# logger.info(...) calls were being silently dropped (root level stayed at
# whatever Lambda's default is, above INFO) despite the line above.
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)

_settings = get_settings()


def _load_telegram_secret() -> dict[str, str]:
    if _settings.telegram_bot_token and _settings.telegram_webhook_secret:
        return {
            "bot_token": _settings.telegram_bot_token,
            "webhook_secret": _settings.telegram_webhook_secret,
        }

    secrets_client = boto3.client("secretsmanager", region_name=_settings.aws_region)
    response = secrets_client.get_secret_value(SecretId=_settings.telegram_secret_name)
    return json.loads(response["SecretString"])


# Everything below runs once per cold start and is reused across warm invocations.
_secret = _load_telegram_secret()
_webhook_secret = _secret["webhook_secret"]

_table = boto3.resource("dynamodb", region_name=_settings.aws_region).Table(
    _settings.dynamodb_table_name
)

_connect_client = ConnectClient(
    connect_boto_client=boto3.client("connect", region_name=_settings.aws_region),
    connect_participant_boto_client=boto3.client(
        "connectparticipant", region_name=_settings.aws_region
    ),
    instance_id=_settings.connect_instance_id,
    contact_flow_id=_settings.connect_contact_flow_id,
    streaming_topic_arn=_settings.chat_events_topic_arn,
)

_chat_service = ChatService(
    session_repository=SessionRepository(table=_table),
    connect_client=_connect_client,
    telegram_client=TelegramClient(bot_token=_secret["bot_token"]),
    session_ttl_seconds=_settings.session_ttl_seconds,
)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    headers = event.get("headers") or {}

    if not validation.verify_secret_token(headers, _webhook_secret):
        logger.warning("telegram_webhook_secret_mismatch")
        return {"statusCode": 403, "body": "forbidden"}

    update = validation.parse_telegram_update(event.get("body", ""))
    if update is None:
        logger.warning(f"telegram_update_unparseable body={event.get('body', '')[:500]!r}")
        return {"statusCode": 200, "body": "ignored"}

    try:
        _chat_service.handle_update(update)
    except Exception:
        logger.exception("telegram_update_processing_failed")

    return {"statusCode": 200, "body": "ok"}
