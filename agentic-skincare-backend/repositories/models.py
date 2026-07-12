from typing import Any

from pydantic import BaseModel

from core.state import TurnStatus


class SkincareSessionRecord(BaseModel):
    """Estado de una conversacion de F_IA_Ventas persistido entre invocaciones
    del Lambda (que en si es stateless -- Connect solo pasa atributos de
    contacto por turno, ver entrypoints/lambda_handler.py).
    """

    # Se conserva el prefijo historico ``contact#`` para no invalidar datos ya
    # almacenados; el sufijo ahora puede ser conversation_id o el ContactId de
    # respaldo.
    pk: str
    messages: list[dict]  # serializado con langchain_core.messages.messages_to_dict
    patient_info: dict[str, Any] = {}
    consecutive_unresolved: int = 0
    turn_status: TurnStatus = "en_progreso"
    ttl: int = 0

    @staticmethod
    def build_pk(conversation_id: str) -> str:
        return f"contact#{conversation_id}"
