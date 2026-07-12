import json

from telegram_inbound_adapter import validation


def test_verify_secret_token_matches():
    headers = {"X-Telegram-Bot-Api-Secret-Token": "expected"}
    assert validation.verify_secret_token(headers, "expected") is True


def test_verify_secret_token_mismatch():
    headers = {"X-Telegram-Bot-Api-Secret-Token": "wrong"}
    assert validation.verify_secret_token(headers, "expected") is False


def test_verify_secret_token_missing_header():
    assert validation.verify_secret_token({}, "expected") is False


def test_parse_telegram_update_valid():
    body = json.dumps(
        {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 123, "username": "alice"},
                "text": "hola",
            },
        }
    )
    update = validation.parse_telegram_update(body)
    assert update is not None
    assert update.message.text == "hola"
    assert update.message.chat.id == 123
    assert update.message.from_.username == "alice"


def test_parse_telegram_update_invalid_json():
    assert validation.parse_telegram_update("not json") is None


def test_parse_telegram_update_invalid_schema():
    assert validation.parse_telegram_update(json.dumps({"foo": "bar"})) is None
