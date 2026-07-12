import time
from decimal import Decimal
from typing import Any

from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict

from repositories.models import SkincareSessionRecord


def _floats_to_decimal(value: Any) -> Any:
    """DynamoDB's Table resource rejects native `float`s outright (`TypeError:
    Float types are not supported`) -- and `messages_to_dict` on a real LLM
    response includes `usage_metadata`/`response_metadata` with float fields
    (token costs, scores, etc.) we never read back, so this walks the
    whole item recursively rather than trying to enumerate every field a
    future model/SDK version might add.
    """
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _floats_to_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_floats_to_decimal(v) for v in value]
    return value


class SessionRepository:
    """Persiste el estado de conversacion de agentic-skincare-backend en
    DynamoDB (tabla `SkincareAgentSessions`, PK=`pk`, sin sort key -- mismo
    patron single-table que `ConversationSessions` en telegram-inbound-adapter).

    La clave logica es ``conversation_id``; el adapter la mantiene estable
    aunque Connect cree un ContactId nuevo. Si no llega, el entrypoint conserva
    compatibilidad usando ContactId como fallback.
    """

    def __init__(self, table: Any, max_stored_messages: int) -> None:
        self._table = table
        self._max_stored_messages = max_stored_messages

    def get_session(self, conversation_id: str) -> SkincareSessionRecord | None:
        pk = SkincareSessionRecord.build_pk(conversation_id)
        response = self._table.get_item(Key={"pk": pk})
        item = response.get("Item")
        if item is None:
            return None

        record = SkincareSessionRecord.model_validate(item)
        if record.ttl <= int(time.time()):
            return None
        return record

    def load_messages(self, conversation_id: str) -> list[BaseMessage]:
        session = self.get_session(conversation_id)
        if session is None:
            return []
        return messages_from_dict(session.messages)

    def save_turn(
        self,
        conversation_id: str,
        messages: list[BaseMessage],
        patient_info: dict,
        consecutive_unresolved: int,
        turn_status: str,
        ttl_seconds: int,
    ) -> None:
        # Solo se guardan los ultimos N mensajes -- acota el tamano del item
        # de DynamoDB y el contexto que se le manda al LLM en el proximo
        # turno (ver core/settings.py: max_stored_messages).
        trimmed = messages[-self._max_stored_messages :]
        record = SkincareSessionRecord(
            pk=SkincareSessionRecord.build_pk(conversation_id),
            messages=messages_to_dict(trimmed),
            patient_info=patient_info,
            consecutive_unresolved=consecutive_unresolved,
            turn_status=turn_status,
            ttl=int(time.time()) + ttl_seconds,
        )
        self._table.put_item(Item=_floats_to_decimal(record.model_dump(mode="json")))
