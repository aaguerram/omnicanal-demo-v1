import logging

from botocore.exceptions import ClientError

from telegram_inbound_adapter.clients.connect_client import ConnectClient
from telegram_inbound_adapter.clients.telegram_client import TelegramClient
from telegram_inbound_adapter.models import SessionRecord, TelegramUpdate
from telegram_inbound_adapter.repositories.session_repository import SessionRepository

logger = logging.getLogger(__name__)

CHANNEL = "telegram"

# Amazon Connect returns AccessDeniedException when the participant connection
# token belongs to a contact that has already ended on the Connect side (e.g.
# idle timeout, agent hangup). The DynamoDB session record's own TTL is much
# longer and doesn't track that, so a session can look ACTIVE here while the
# underlying Connect contact is already gone. That specific error is the only
# case where starting a fresh contact is the right response; any other error
# (throttling, network issues, bugs) must propagate instead of being silently
# reinterpreted as "stale session".
STALE_SESSION_ERROR_CODES = {"AccessDeniedException"}


class ChatService:
    def __init__(
        self,
        session_repository: SessionRepository,
        connect_client: ConnectClient,
        telegram_client: TelegramClient,
        session_ttl_seconds: int,
    ) -> None:
        self._sessions = session_repository
        self._connect = connect_client
        self._telegram = telegram_client
        self._ttl_seconds = session_ttl_seconds

    def handle_update(self, update: TelegramUpdate) -> None:
        # NOTE: logger.info(msg, extra={...}) does NOT put the extra fields
        # into the CloudWatch text output -- the default logging.Formatter
        # only renders %(message)s, silently dropping `extra`. Everything we
        # actually need to see goes directly into the message string instead.
        message = update.message
        if message is None or not message.text:
            logger.info(f"telegram_update_ignored update_id={update.update_id}")
            return

        chat_id = message.chat.id
        external_user_id = str(chat_id)
        username = message.from_.username if message.from_ else None
        display_name = username or external_user_id

        session = self._sessions.get_active_session(CHANNEL, external_user_id)
        logger.info(
            f"telegram_update_received chat_id={chat_id} update_id={update.update_id} "
            f"has_active_session={session is not None} "
            f"connect_contact_id={session.connect_contact_id if session else None} "
            f"text={message.text[:200]!r}"
        )

        try:
            if session is not None:
                try:
                    self._connect.send_message(session.connection_token, message.text)
                    logger.info(
                        f"sent_message_to_existing_session chat_id={chat_id} "
                        f"connect_contact_id={session.connect_contact_id}"
                    )
                    return
                except ClientError as exc:
                    error_code = exc.response.get("Error", {}).get("Code")
                    if error_code not in STALE_SESSION_ERROR_CODES:
                        raise
                    logger.warning(
                        f"stale_session_reconnecting chat_id={chat_id} "
                        f"update_id={update.update_id}"
                    )

            # message.text travels only as the initialMessage contact
            # attribute (see _create_session) -- no SendMessage/InitialMessage
            # call here, on purpose (see connect_client.py's start_chat_contact).
            session = self._create_session(external_user_id, display_name, username, message.text)
            logger.info(
                f"seeded_initial_message_for_new_session chat_id={chat_id} "
                f"connect_contact_id={session.connect_contact_id}"
            )
        except Exception:
            logger.exception(f"chat_service_failed chat_id={chat_id} update_id={update.update_id}")
            self._telegram.send_message(
                chat_id,
                "No pudimos conectar tu mensaje con un agente. Intenta de nuevo en unos minutos.",
            )
            raise

    def _create_session(
        self, external_user_id: str, display_name: str, username: str | None, initial_message: str
    ) -> SessionRecord:
        # initialMessage attribute lets F_Menu_Router classify this exact
        # message directly (InvokeLambdaFunction reading
        # $.Attributes.initialMessage) instead of prompting with
        # "Contanos brevemente..." and waiting on GetParticipantInput -- the
        # customer already said something to trigger this contact, so
        # there's nothing to wait for on this first turn. Deliberately NOT
        # also sent as a chat message (no StartChatContact InitialMessage,
        # no SendMessage here) -- see connect_client.py's start_chat_contact
        # for why a real leftover customer message breaks the FIRST
        # GetParticipantInput the contact ever runs into (F_Menu_Reintento's,
        # if intent isn't detected).
        contact = self._connect.start_chat_contact(
            display_name=display_name,
            attributes={
                "channel": CHANNEL,
                "telegramUserId": external_user_id,
                "telegramUsername": username or "",
                "source": "telegram_bot",
                "conversationState": "new",
                "initialMessage": initial_message,
            },
        )
        logger.info(f"start_chat_contact_ok connect_contact_id={contact.contact_id}")

        # Streaming is started immediately after StartChatContact, before
        # CreateParticipantConnection -- the flow (e.g. F_Menu_Reintento's
        # prompt, or F_Handoff_Humano's "Gracias...") can start producing
        # participant messages as soon as the contact exists, and anything
        # sent before streaming is active would never reach the streaming
        # SNS topic (and so never reach Telegram).
        streaming_id = self._connect.start_contact_streaming(contact.contact_id)
        logger.info(
            f"start_contact_streaming_ok connect_contact_id={contact.contact_id} "
            f"streaming_id={streaming_id}"
        )

        connection_token = self._connect.create_participant_connection(contact.participant_token)
        logger.info(f"create_participant_connection_ok connect_contact_id={contact.contact_id}")

        session = SessionRecord(
            pk=SessionRecord.build_pk(CHANNEL, external_user_id),
            channel=CHANNEL,
            external_user_id=external_user_id,
            connect_contact_id=contact.contact_id,
            participant_id=contact.participant_id,
            participant_token=contact.participant_token,
            connection_token=connection_token,
            ttl=0,
        )
        self._sessions.put_session(session, ttl_seconds=self._ttl_seconds)
        return session
