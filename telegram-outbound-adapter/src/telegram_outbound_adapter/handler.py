import json
import logging
from typing import Any

import boto3

from telegram_outbound_adapter.clients.telegram_client import TelegramClient
from telegram_outbound_adapter.models import ConnectStreamingMessage
from telegram_outbound_adapter.repositories.session_repository import SessionRepository
from telegram_outbound_adapter.settings import get_settings

logging.basicConfig(level=logging.INFO)
# basicConfig() is a no-op if the root logger already has handlers -- and the
# Lambda Python runtime pre-attaches one before our code ever runs, so
# logger.info(...) calls were being silently dropped (root level stayed at
# whatever Lambda's default is, above INFO) despite the line above.
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)

_settings = get_settings()

# Amazon Connect real-time contact streaming publishes every event on the
# contact (customer messages, agent messages, flow prompts, join/leave,
# disconnect) to the same SNS topic. Everything except the customer's own
# messages should be relayed back to Telegram -- that includes AGENT/BOT
# replies but also SYSTEM messages, which is the role Connect attributes to
# text sent by a flow's "Message participant" / "Get customer input" blocks
# (e.g. F_Menu_Router's menu prompt in telegram-inbound-adapter). Only
# CUSTOMER is excluded, since relaying that would echo the user's own text
# back to them.
EXCLUDED_PARTICIPANT_ROLES = {"CUSTOMER"}
CHAT_ENDED_CONTENT_TYPE = "application/vnd.amazonaws.connect.event.chat.ended"


def _load_bot_token() -> str:
    if _settings.telegram_bot_token:
        return _settings.telegram_bot_token

    secrets_client = boto3.client("secretsmanager", region_name=_settings.aws_region)
    response = secrets_client.get_secret_value(SecretId=_settings.telegram_secret_name)
    return json.loads(response["SecretString"])["bot_token"]


# Everything below runs once per cold start and is reused across warm invocations.
_table = boto3.resource("dynamodb", region_name=_settings.aws_region).Table(
    _settings.dynamodb_table_name
)
_sessions = SessionRepository(table=_table)
_telegram_client = TelegramClient(bot_token=_load_bot_token())


def _handle_message(message: ConnectStreamingMessage) -> None:
    # NOTE: logger.info(msg, extra={...}) does NOT put the extra fields into
    # the CloudWatch text output -- the default logging.Formatter only
    # renders %(message)s, silently dropping `extra`. Everything we actually
    # need to see goes directly into the message string instead.
    logger.info(
        f"outbound_message_received contact_id={message.contact_id} "
        f"role={message.participant_role} type={message.type} "
        f"content_type={message.content_type} "
        f"content={(message.content or '')[:200]!r}"
    )

    lookup = _sessions.get_channel_and_user_by_contact(message.contact_id)
    if lookup is None:
        logger.warning(f"outbound_unknown_contact contact_id={message.contact_id}")
        return
    channel, external_user_id = lookup
    logger.info(
        f"outbound_contact_resolved contact_id={message.contact_id} "
        f"channel={channel} external_user_id={external_user_id}"
    )

    if message.content_type == CHAT_ENDED_CONTENT_TYPE:
        logger.info(f"outbound_marking_session_ended contact_id={message.contact_id}")
        _sessions.mark_ended(channel, external_user_id)
        return

    if message.participant_role in EXCLUDED_PARTICIPANT_ROLES:
        logger.info(
            f"outbound_skipped_excluded_role contact_id={message.contact_id} "
            f"role={message.participant_role}"
        )
        return
    if message.type != "MESSAGE" or not message.content:
        logger.info(
            f"outbound_skipped_not_a_message contact_id={message.contact_id} "
            f"type={message.type}"
        )
        return

    if channel == "telegram":
        logger.info(
            f"outbound_sending_to_telegram chat_id={external_user_id} "
            f"content={message.content[:200]!r}"
        )
        _telegram_client.send_message(int(external_user_id), message.content)
        logger.info(f"outbound_sent_to_telegram chat_id={external_user_id}")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    records = event.get("Records", [])
    logger.info(f"outbound_invocation_started record_count={len(records)}")
    for record in records:
        raw_message = record.get("Sns", {}).get("Message", "{}")
        try:
            message = ConnectStreamingMessage.model_validate(json.loads(raw_message))
        except Exception:
            logger.exception(f"outbound_message_parse_failed raw_message={raw_message[:800]!r}")
            continue

        try:
            _handle_message(message)
        except Exception:
            logger.exception(f"outbound_message_processing_failed contact_id={message.contact_id}")

    return {"statusCode": 200}
