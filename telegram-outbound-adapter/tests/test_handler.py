import json
import os
from unittest.mock import MagicMock

os.environ.setdefault("DYNAMODB_TABLE_NAME", "ConversationSessions")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

import pytest

from telegram_outbound_adapter import handler


@pytest.fixture(autouse=True)
def stub_dependencies(monkeypatch):
    sessions = MagicMock()
    telegram_client = MagicMock()
    monkeypatch.setattr(handler, "_sessions", sessions)
    monkeypatch.setattr(handler, "_telegram_client", telegram_client)
    return sessions, telegram_client


def _sns_event(message: dict) -> dict:
    return {"Records": [{"Sns": {"Message": json.dumps(message)}}]}


def test_relays_agent_message_to_telegram(stub_dependencies):
    sessions, telegram_client = stub_dependencies
    sessions.get_channel_and_user_by_contact.return_value = ("telegram", "123")

    event = _sns_event(
        {
            "ContactId": "contact-1",
            "ParticipantRole": "AGENT",
            "Type": "MESSAGE",
            "Content": "Hola, en que puedo ayudarte?",
            "ContentType": "text/plain",
        }
    )

    handler.lambda_handler(event, None)

    telegram_client.send_message.assert_called_once_with(123, "Hola, en que puedo ayudarte?")
    sessions.mark_ended.assert_not_called()


def test_relays_system_message_to_telegram(stub_dependencies):
    # SYSTEM is the role Connect attributes to text sent by a flow's
    # "Message participant" / "Get customer input" blocks (e.g. the
    # F_Menu_Router menu prompt in telegram-inbound-adapter) -- these must
    # reach the user too, not just AGENT replies.
    sessions, telegram_client = stub_dependencies
    sessions.get_channel_and_user_by_contact.return_value = ("telegram", "123")

    event = _sns_event(
        {
            "ContactId": "contact-1",
            "ParticipantRole": "SYSTEM",
            "Type": "MESSAGE",
            "Content": "Elige una opcion: 1) Atencion 2) Soporte 3) Ventas 4) Cobranza",
            "ContentType": "text/plain",
        }
    )

    handler.lambda_handler(event, None)

    telegram_client.send_message.assert_called_once_with(
        123, "Elige una opcion: 1) Atencion 2) Soporte 3) Ventas 4) Cobranza"
    )


def test_ignores_customer_message(stub_dependencies):
    sessions, telegram_client = stub_dependencies
    sessions.get_channel_and_user_by_contact.return_value = ("telegram", "123")

    event = _sns_event(
        {
            "ContactId": "contact-1",
            "ParticipantRole": "CUSTOMER",
            "Type": "MESSAGE",
            "Content": "hola",
            "ContentType": "text/plain",
        }
    )

    handler.lambda_handler(event, None)

    telegram_client.send_message.assert_not_called()


def test_marks_session_ended_on_chat_ended_event(stub_dependencies):
    sessions, telegram_client = stub_dependencies
    sessions.get_channel_and_user_by_contact.return_value = ("telegram", "123")

    event = _sns_event(
        {
            "ContactId": "contact-1",
            "ParticipantRole": "SYSTEM",
            "Type": "EVENT",
            "ContentType": "application/vnd.amazonaws.connect.event.chat.ended",
        }
    )

    handler.lambda_handler(event, None)

    sessions.mark_ended.assert_called_once_with("telegram", "123")
    telegram_client.send_message.assert_not_called()


def test_unknown_contact_id_is_a_noop(stub_dependencies):
    sessions, telegram_client = stub_dependencies
    sessions.get_channel_and_user_by_contact.return_value = None

    event = _sns_event(
        {
            "ContactId": "unknown-contact",
            "ParticipantRole": "AGENT",
            "Type": "MESSAGE",
            "Content": "hola",
            "ContentType": "text/plain",
        }
    )

    response = handler.lambda_handler(event, None)

    assert response["statusCode"] == 200
    telegram_client.send_message.assert_not_called()
    sessions.mark_ended.assert_not_called()


def test_malformed_sns_message_does_not_raise(stub_dependencies):
    event = {"Records": [{"Sns": {"Message": "not json"}}]}

    response = handler.lambda_handler(event, None)

    assert response["statusCode"] == 200
