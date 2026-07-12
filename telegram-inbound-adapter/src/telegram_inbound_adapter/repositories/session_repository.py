import time
from typing import Any

from telegram_inbound_adapter.models import SessionRecord, SessionStatus


class SessionRepository:
    def __init__(self, table: Any) -> None:
        self._table = table

    def get_active_session(self, channel: str, external_user_id: str) -> SessionRecord | None:
        pk = SessionRecord.build_pk(channel, external_user_id)
        response = self._table.get_item(Key={"pk": pk})
        item = response.get("Item")
        if item is None:
            return None

        record = SessionRecord.model_validate(item)
        if record.status != SessionStatus.ACTIVE:
            return None
        if record.ttl <= int(time.time()):
            return None
        return record

    def put_session(self, record: SessionRecord, ttl_seconds: int) -> None:
        ttl = int(time.time()) + ttl_seconds
        record.ttl = ttl
        item = record.model_dump(mode="json")
        self._table.put_item(Item=item)

        # Secondary index item so the outbound Lambda can resolve "which
        # Telegram chat does this Connect ContactId belong to" with a plain
        # GetItem instead of a GSI.
        self._table.put_item(
            Item={
                "pk": self._contact_index_pk(record.connect_contact_id),
                "channel": record.channel,
                "external_user_id": record.external_user_id,
                "ttl": ttl,
            }
        )

    @staticmethod
    def _contact_index_pk(connect_contact_id: str) -> str:
        return f"contact#{connect_contact_id}"
