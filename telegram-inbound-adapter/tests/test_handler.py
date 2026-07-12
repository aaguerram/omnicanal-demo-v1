import json
import os
from unittest.mock import MagicMock

os.environ.setdefault("CONNECT_INSTANCE_ID", "instance-1")
os.environ.setdefault("CONNECT_CONTACT_FLOW_ID", "flow-1")
os.environ.setdefault("CHAT_EVENTS_TOPIC_ARN", "arn:aws:sns:us-east-1:042278586355:test-topic")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("DYNAMODB_TABLE_NAME", "ConversationSessions")

import pytest

from telegram_inbound_adapter import handler


@pytest.fixture(autouse=True)
def stub_chat_service(monkeypatch):
    stub = MagicMock()
    monkeypatch.setattr(handler, "_chat_service", stub)
    return stub


def _event(body: dict, secret: str = "test-secret") -> dict:
    return {
        "headers": {"X-Telegram-Bot-Api-Secret-Token": secret},
        "body": json.dumps(body),
    }


def test_rejects_invalid_secret_token(stub_chat_service):
    response = handler.lambda_handler(_event({"update_id": 1}, secret="wrong"), None)

    assert response["statusCode"] == 403
    stub_chat_service.handle_update.assert_not_called()


def test_ignores_unparseable_body(stub_chat_service):
    event = {"headers": {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}, "body": "not json"}

    response = handler.lambda_handler(event, None)

    assert response["statusCode"] == 200
    stub_chat_service.handle_update.assert_not_called()


def test_delegates_valid_update_to_chat_service(stub_chat_service):
    body = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": 123, "type": "private"},
            "text": "hola",
        },
    }

    response = handler.lambda_handler(_event(body), None)

    assert response["statusCode"] == 200
    stub_chat_service.handle_update.assert_called_once()


def test_returns_200_even_if_chat_service_raises(stub_chat_service):
    stub_chat_service.handle_update.side_effect = RuntimeError("boom")
    body = {
        "update_id": 1,
        "message": {"message_id": 1, "chat": {"id": 1, "type": "private"}, "text": "x"},
    }

    response = handler.lambda_handler(_event(body), None)

    assert response["statusCode"] == 200
