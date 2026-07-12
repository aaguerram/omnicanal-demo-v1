"""Lambda entrypoint directa para agentic-skincare-backend -- ya NO se
despliega en la cuenta real (el hosting se movio a Bedrock AgentCore Runtime,
invocado desde F_IA_Ventas a traves del proyecto hermano
agentic-skincare-adapter, ver entrypoints/agentcore_app.py y
../context.md). Se deja para pruebas directas/locales del contrato sin
depender de AgentCore.

Contrato (igual que connect-nlu-router-menu, en caso de que algo la invoque
como Lambda cruda):
1. Invocacion directa: ``event = {"conversation_id": "...",
   "contact_id": "...", "message": "..."}``.
2. Bloque "Invoke AWS Lambda function" de Connect: los parametros viajan en
   ``event["Details"]["Parameters"]``, junto a ``event["Details"]["ContactData"]``
   (de ahi tambien se lee el ContactId real si el flow no lo paso explicito).

Responde un STRING_MAP plano (Connect exige ResponseValidation=STRING_MAP):
``{"response_text": "...", "status": "en_progreso|finalizado|no_resuelto",
"escalate": "true"|"false"}``.
"""

import logging
from typing import Any

logging.basicConfig(level=logging.INFO)
# basicConfig() es un no-op si el root logger ya tiene handlers -- y el
# runtime de Lambda le adjunta uno antes de que corra nuestro codigo, asi que
# logger.info(...) quedaba mudo pese a la linea de arriba. Mismo fix que en
# telegram-inbound-adapter/telegram-outbound-adapter/connect-nlu-router-menu
# -- ver ../context.md, gotcha #1.
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)

from core.turn_service import process_turn  # noqa: E402


def _extract_conversation_id_and_message(
    event: dict[str, Any] | None,
) -> tuple[str | None, str]:
    event = event or {}
    details = event.get("Details")
    if isinstance(details, dict):
        params = details.get("Parameters", {}) or {}
        conversation_id = (
            params.get("conversation_id")
            or params.get("contact_id")
            or details.get("ContactData", {}).get("ContactId")
        )
        return conversation_id, params.get("message", "")
    return event.get("conversation_id") or event.get("contact_id"), event.get("message", "")


# Alias temporal para consumidores locales que importaban este helper.
_extract_contact_id_and_message = _extract_conversation_id_and_message


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    conversation_id, message = _extract_conversation_id_and_message(event)
    result = process_turn(conversation_id, message)
    return {
        "response_text": result["response_text"],
        "status": result["status"],
        "escalate": "true" if result["escalate"] else "false",
    }
