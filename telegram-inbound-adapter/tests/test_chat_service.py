from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from telegram_inbound_adapter.clients.connect_client import ChatContact
from telegram_inbound_adapter.models import (
    TelegramChat,
    TelegramFrom,
    TelegramMessage,
    TelegramUpdate,
)
from telegram_inbound_adapter.services.chat_service import ChatService


def access_denied_error(operation: str = "SendMessage") -> ClientError:
    return ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}}, operation
    )


def make_update(text: str = "hola", chat_id: int = 123, username: str = "alice") -> TelegramUpdate:
    return TelegramUpdate(
        update_id=1,
        message=TelegramMessage(
            message_id=10,
            chat=TelegramChat(id=chat_id, type="private"),
            **{"from": TelegramFrom(id=chat_id, username=username)},
            text=text,
        ),
    )


@pytest.fixture
def connect_client():
    client = MagicMock()
    client.start_chat_contact.return_value = ChatContact(
        contact_id="contact-1",
        participant_id="participant-1",
        participant_token="participant-token",
    )
    client.create_participant_connection.return_value = "connection-token"
    return client


@pytest.fixture
def telegram_client():
    return MagicMock()


@pytest.fixture
def chat_service(session_repository, connect_client, telegram_client):
    return ChatService(
        session_repository=session_repository,
        connect_client=connect_client,
        telegram_client=telegram_client,
        session_ttl_seconds=3600,
    )


def test_handle_update_creates_session_when_missing(
    chat_service, connect_client, session_repository, dynamodb_table
):
    update = make_update()

    chat_service.handle_update(update)

    connect_client.start_chat_contact.assert_called_once()
    call_kwargs = connect_client.start_chat_contact.call_args.kwargs
    attributes = call_kwargs["attributes"]
    assert attributes["channel"] == "telegram"
    assert attributes["conversationState"] == "new"
    # The message travels ONLY as this attribute, never as an actual chat
    # message (no InitialMessage, no SendMessage) -- see connect_client.py's
    # start_chat_contact for why a real leftover customer message breaks the
    # first GetParticipantInput the contact runs into.
    assert attributes["initialMessage"] == "hola"
    connect_client.create_participant_connection.assert_called_once_with("participant-token")
    connect_client.start_contact_streaming.assert_called_once_with("contact-1")
    connect_client.send_message.assert_not_called()
    assert session_repository.get_active_session("telegram", "123") is not None

    # contact#<id> secondary index, written for telegram-outbound-adapter to
    # resolve "which Telegram chat does this Connect ContactId belong to".
    index_item = dynamodb_table.get_item(Key={"pk": "contact#contact-1"})["Item"]
    assert index_item["channel"] == "telegram"
    assert index_item["external_user_id"] == "123"


def test_handle_update_reuses_existing_session(chat_service, connect_client, session_repository):
    chat_service.handle_update(make_update(text="primero"))
    connect_client.start_chat_contact.reset_mock()
    connect_client.create_participant_connection.reset_mock()

    chat_service.handle_update(make_update(text="segundo"))

    connect_client.start_chat_contact.assert_not_called()
    connect_client.create_participant_connection.assert_not_called()
    connect_client.send_message.assert_called_with("connection-token", "segundo")


def test_handle_update_reconnects_when_existing_session_send_fails(
    chat_service, connect_client, session_repository
):
    chat_service.handle_update(make_update(text="primero"))
    connect_client.start_chat_contact.reset_mock()
    connect_client.create_participant_connection.reset_mock()
    connect_client.send_message.reset_mock()

    # Send fails with AccessDeniedException (stale connection token from an
    # ended Connect contact) -- the retry starts a fresh contact and seeds
    # "segundo" as that new contact's initialMessage attribute, not another
    # SendMessage call.
    connect_client.send_message.side_effect = [access_denied_error()]
    connect_client.start_chat_contact.return_value = ChatContact(
        contact_id="contact-2",
        participant_id="participant-2",
        participant_token="participant-token-2",
    )
    connect_client.create_participant_connection.return_value = "connection-token-2"

    chat_service.handle_update(make_update(text="segundo"))

    connect_client.start_chat_contact.assert_called_once()
    attrs = connect_client.start_chat_contact.call_args.kwargs["attributes"]
    assert attrs["initialMessage"] == "segundo"
    connect_client.create_participant_connection.assert_called_once_with("participant-token-2")
    connect_client.send_message.assert_called_once()

    session = session_repository.get_active_session("telegram", "123")
    assert session.connect_contact_id == "contact-2"


def test_handle_update_does_not_reconnect_on_unrelated_client_error(
    chat_service, connect_client, telegram_client, session_repository
):
    chat_service.handle_update(make_update(text="primero"))
    connect_client.start_chat_contact.reset_mock()
    connect_client.create_participant_connection.reset_mock()
    connect_client.send_message.reset_mock()

    throttling_error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "SendMessage"
    )
    connect_client.send_message.side_effect = throttling_error

    with pytest.raises(ClientError):
        chat_service.handle_update(make_update(text="segundo"))

    connect_client.start_chat_contact.assert_not_called()
    connect_client.send_message.assert_called_once_with("connection-token", "segundo")
    telegram_client.send_message.assert_called_once()


def test_handle_update_ignores_non_text_message(chat_service, connect_client):
    update = TelegramUpdate(update_id=2, message=None)

    chat_service.handle_update(update)

    connect_client.start_chat_contact.assert_not_called()
    connect_client.send_message.assert_not_called()


def test_handle_update_notifies_and_raises_on_failure(
    chat_service, connect_client, telegram_client
):
    # New session (no send_message call in this path anymore, see
    # test_handle_update_creates_session_when_missing) -- fail on contact
    # creation itself to exercise the same notify-and-raise behavior.
    connect_client.start_chat_contact.side_effect = RuntimeError("boom")
    update = make_update()

    with pytest.raises(RuntimeError):
        chat_service.handle_update(update)

    telegram_client.send_message.assert_called_once()
