"""Logica de turno de Luna (agentic-skincare-backend), compartida por ambos
entrypoints -- entrypoints/lambda_handler.py (Lambda directa, ya no
desplegada, se deja para pruebas locales/directas) y
entrypoints/agentcore_app.py (Bedrock AgentCore Runtime, el que se despliega
hoy, invocado por el proyecto hermano agentic-skincare-adapter). Ver
../context.md y el README de este proyecto para el porque del cambio de
hosting -- el contrato de turno (mensaje -> respuesta/estado/escalamiento) no
cambio, solo quien lo hostea.

Note (see .agents/rules/ai-rules.md, seccion 16): message content y
patient_info (sintomas, alergias) NUNCA se loguean aca, solo longitudes y
metadata de control-flow -- son datos de salud/sensibles.
"""

import logging
import os
from typing import Any

import boto3
from langchain_core.messages import AIMessage, HumanMessage

from core.settings import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()


def _load_gcp_credentials() -> None:
    """Carga el JSON de la service account de GCP desde Secrets Manager a un
    archivo temporal y apunta GOOGLE_APPLICATION_CREDENTIALS ahi, para que el
    cliente de Firestore (construido lazy dentro de
    features/info_productos/graph.py, el unico nodo que todavia toca GCP)
    pueda autenticar via ADC. No-op si la env var ya esta seteada (p. ej.
    local con `gcloud auth application-default login`).
    """
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return

    secrets_client = boto3.client("secretsmanager", region_name=_settings.aws_region)
    response = secrets_client.get_secret_value(SecretId=_settings.gcp_secret_name)
    credentials_path = "/tmp/gcp-service-account.json"
    with open(credentials_path, "w", encoding="utf-8") as f:
        f.write(response["SecretString"])
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", _settings.google_cloud_project)


# Todo lo de abajo corre una vez por cold start y se reusa entre invocaciones
# calientes. Las credenciales deben cargarse antes del primer app_graph.invoke(),
# pero core.main_graph es seguro de importar antes -- build_graph() solo conecta
# nodos, nunca construye un cliente LLM en tiempo de import (cada nodo lo hace
# lazy, ver features/*/graph.py).
_load_gcp_credentials()

from core.main_graph import app_graph  # noqa: E402
from repositories.session_repository import SessionRepository  # noqa: E402

_table = boto3.resource("dynamodb", region_name=_settings.aws_region).Table(
    _settings.dynamodb_table_name
)
_sessions = SessionRepository(table=_table, max_stored_messages=_settings.max_stored_messages)

_FALLBACK_RESPONSE = (
    "Tuvimos un inconveniente tecnico de nuestro lado. Te voy a conectar con "
    "un asesor para que te ayude directamente."
)
_END_CONVERSATION_RESPONSE = (
    "Entendido. Gracias por conversar con Luna. He finalizado este chat. "
    "Tu proximo mensaje comenzara desde el menu inicial."
)
_MAX_RESPONSE_CHARS = 6000  # limite total del texto Play prompt/MessageParticipant de Connect


def _response_text(result: dict[str, Any]) -> str:
    messages = result.get("messages", [])
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    if last_ai is None:
        return _FALLBACK_RESPONSE

    content = last_ai.content
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = " ".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    else:
        text = str(content)
    return (text or _FALLBACK_RESPONSE)[:_MAX_RESPONSE_CHARS]


def process_turn(conversation_id: str | None, message: str) -> dict[str, Any]:
    """Procesa un turno de conversacion. Nunca propaga excepciones -- cualquier
    falla (Bedrock caido, Firestore caido, DynamoDB, estado inesperado)
    degrada a una disculpa generica con escalate=True, para que ningun
    llamador (Lambda directa, adapter de AgentCore) tenga que distinguir
    "error tecnico" de "no pude ayudarte".

    Devuelve {"response_text": str, "status": "en_progreso"|"finalizado"|"no_resuelto",
    "escalate": bool, "end_conversation": bool} -- la serializacion a
    STRING_MAP (Connect exige "true"/"false" como string) es responsabilidad
    de quien llama.
    """
    logger.info(
        "skincare_turn_received has_conversation_id=%s message_len=%s",
        conversation_id is not None,
        len(message or ""),
    )

    if not message or not message.strip():
        return {
            "response_text": "",
            "status": "en_progreso",
            "escalate": False,
            "end_conversation": False,
        }

    try:
        prior_messages = _sessions.load_messages(conversation_id) if conversation_id else []
        prior_session = _sessions.get_session(conversation_id) if conversation_id else None
        patient_info = prior_session.patient_info if prior_session else {}
        consecutive_unresolved = prior_session.consecutive_unresolved if prior_session else 0

        initial_state = {
            "messages": prior_messages + [HumanMessage(content=message)],
            "patient_info": patient_info,
        }
        result = app_graph.invoke(initial_state)

        turn_status = result.get("turn_status", "en_progreso")
        end_conversation = result.get("end_conversation", False) is True
        if end_conversation:
            # Una solicitud explicita de cierre resuelve el objetivo actual,
            # pero no es un escalamiento a un humano. La senal separada evita
            # confundirla con cualquier turno simplemente "finalizado".
            turn_status = "finalizado"
        consecutive_unresolved = consecutive_unresolved + 1 if turn_status == "no_resuelto" else 0
        # ``finalizado`` significa que Luna resolvio el objetivo de este
        # turno, no que haga falta pagar/esperar una atencion humana. El modo
        # skincare sigue vigente y los mensajes posteriores vuelven al mismo
        # AgentCore. Solo se deriva por incapacidad repetida o falla tecnica.
        escalate = (
            not end_conversation and consecutive_unresolved >= _settings.max_consecutive_unresolved
        )

        if conversation_id:
            _sessions.save_turn(
                conversation_id=conversation_id,
                messages=result.get("messages", []),
                patient_info=result.get("patient_info", patient_info),
                consecutive_unresolved=consecutive_unresolved,
                turn_status=turn_status,
                ttl_seconds=_settings.session_ttl_seconds,
            )

        logger.info(
            "skincare_turn_processed status=%s consecutive_unresolved=%s "
            "end_conversation=%s escalate=%s",
            turn_status,
            consecutive_unresolved,
            end_conversation,
            escalate,
        )
        return {
            "response_text": (
                _END_CONVERSATION_RESPONSE if end_conversation else _response_text(result)
            ),
            "status": turn_status,
            "escalate": escalate,
            "end_conversation": end_conversation,
        }
    except Exception:
        logger.exception("skincare_turn_failed")
        return {
            "response_text": _FALLBACK_RESPONSE,
            "status": "no_resuelto",
            "escalate": True,
            "end_conversation": False,
        }
