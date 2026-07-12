from typing import Any

from telegram_outbound_adapter.models import SessionStatus


class SessionRepository:
    """Reads/updates the ConversationSessions table written by
    telegram-inbound-adapter. The item shapes (pk formats, field names) are
    a contract shared between both services -- see that project's
    SessionRepository.put_session for where the `telegram#<chat_id>` and
    `contact#<connect_contact_id>` items are written.
    """

    def __init__(self, table: Any) -> None:
        self._table = table

    def get_channel_and_user_by_contact(self, connect_contact_id: str) -> tuple[str, str] | None:
        response = self._table.get_item(Key={"pk": f"contact#{connect_contact_id}"})
        item = response.get("Item")
        if item is None:
            return None
        return item["channel"], item["external_user_id"]

    def mark_ended(self, channel: str, external_user_id: str) -> None:
        pk = f"{channel}#{external_user_id}"
        self._table.update_item(
            Key={"pk": pk},
            UpdateExpression="SET #status = :ended",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":ended": SessionStatus.ENDED.value},
        )
