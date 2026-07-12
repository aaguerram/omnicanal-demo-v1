from typing import TypedDict, Annotated, Literal, Optional, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

# Emitido por core/estado_turno.py al final de cada turno. Lo consume el
# Lambda handler (entrypoints/lambda_handler.py) para decidir si la
# conversacion debe escalar a un asesor humano (ver esa docstring para el
# contrato completo: "finalizado" o 3 "no_resuelto" seguidos -> escalate).
TurnStatus = Literal["en_progreso", "finalizado", "no_resuelto"]

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    image_url: Optional[str]
    patient_info: Dict[str, Any]  # e.g., {"acne_level": "alto", "skin_type": "grasa", "irritation": "no", "allergies": "ninguna"}
    next_step: str # To help router determine the next node
    turn_status: TurnStatus
