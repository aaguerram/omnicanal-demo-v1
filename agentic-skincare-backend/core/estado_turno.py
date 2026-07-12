import json
from typing import Any, Literal

from dotenv import load_dotenv
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.settings import get_settings
from core.state import AgentState

load_dotenv()


class TurnStatusResult(BaseModel):
    status: Literal["en_progreso", "finalizado", "no_resuelto"] = Field(
        description=(
            "'finalizado' si ya se dio una recomendacion de producto concreta o "
            "un resumen del diagnostico y el objetivo actual quedo resuelto. "
            "'no_resuelto' si "
            "el pedido del cliente esta fuera del alcance de un asistente de "
            "cuidado de la piel/productos (no es algo que este asistente pueda "
            "responder). 'en_progreso' si la conversacion sigue en curso "
            "normalmente (preguntas de seguimiento, falta informacion)."
        )
    )


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return " ".join(p for p in parts if p)
    return str(content)


SYSTEM_PROMPT = """
Evaluas el estado de una conversacion de un asistente virtual de skincare/ventas
(Luna) que atiende al cliente directamente.

Tu unica tarea es clasificar el ESTADO DEL TURNO que acaba de terminar en
exactamente una de estas tres categorias:

- finalizado: Luna ya dio una recomendacion de producto concreta, o ya resumio
  el diagnostico de piel del cliente, y el objetivo de este turno quedo
  resuelto. Los mensajes futuros pueden continuar con Luna.
- no_resuelto: el pedido del cliente no es algo que un asistente de cuidado de
  la piel o informacion de productos pueda resolver (por ejemplo: reclamos,
  facturacion, temas no relacionados a skincare/productos, o el cliente pide
  explicitamente hablar con una persona).
- en_progreso: la conversacion sigue normalmente -- Luna esta haciendo
  preguntas de seguimiento o todavia falta informacion antes de poder ayudar.

Respondes solo con la categoria, sin texto adicional.
"""


def evaluar_estado_node(state: AgentState) -> dict[str, Any]:
    messages = state.get("messages", [])
    if not messages:
        return {"turn_status": "en_progreso"}

    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    if last_ai is None or not _message_text(last_ai).strip():
        return {"turn_status": "en_progreso"}

    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    patient_info = state.get("patient_info", {})

    last_human_text = _message_text(last_human) if last_human else "(ninguno)"
    patient_info_json = json.dumps(patient_info, ensure_ascii=False)
    transcript = (
        f"Ultimo mensaje del cliente: {last_human_text}\n"
        f"Respuesta de Luna: {_message_text(last_ai)}\n"
        f"Datos del paciente recopilados hasta ahora: {patient_info_json}"
    )

    settings = get_settings()
    llm = ChatBedrockConverse(
        model_id=settings.nova_model_id,
        region_name=settings.aws_region,
        temperature=0.0,
        max_tokens=1470,
    )
    structured_llm = llm.with_structured_output(TurnStatusResult)

    try:
        response = structured_llm.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=transcript)]
        )
        return {"turn_status": response.status}
    except Exception as e:
        # Nunca debe tirar la conversacion completa por un fallo de este
        # clasificador -- se sigue tratando como en curso, el Lambda handler
        # decide el escalamiento solo con base en el contador de intentos.
        print(f"Error in estado_turno: {e}")
        return {"turn_status": "en_progreso"}
