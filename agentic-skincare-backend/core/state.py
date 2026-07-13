from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

# Emitido por core/estado_turno.py al final de cada turno. Lo consume
# core/turn_service.py para decidir si la conversacion debe escalar a un
# asesor humano o si el cliente pidio cerrarla explicitamente.
TurnStatus = Literal["en_progreso", "finalizado", "no_resuelto"]


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    image_url: str | None
    # e.g. acne_level, skin_type, irritation y allergies
    patient_info: dict[str, Any]
    next_step: str  # To help router determine the next node
    turn_status: TurnStatus
    end_conversation: bool
