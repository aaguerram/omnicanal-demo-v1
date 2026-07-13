"""Entrypoint de agentic-skincare-backend para Amazon Bedrock AgentCore
Runtime -- este es el que se despliega hoy contra la cuenta real (ver
../context.md y README.md), invocado por el proyecto hermano
agentic-skincare-adapter (Lambda delgada asociada a
F_IA_Ventas en Amazon Connect) via
`bedrock-agentcore:InvokeAgentRuntime`, nunca directo desde Connect (Connect
solo sabe invocar Lambdas).

Contrato del payload (lo arma agentic-skincare-adapter, no Connect
directamente): ``{"conversation_id": "...", "contact_id": "...",
"message": "..."}``. ``conversation_id`` mantiene el historial aunque
Connect cree otro contacto; ``contact_id`` es el fallback compatible. Responde
``{"response_text": "...", "status": "en_progreso|finalizado|no_resuelto",
"escalate": true|false, "end_conversation": true|false}`` -- sin la
restriccion STRING_MAP de Connect (eso lo resuelve el adapter al traducir esta
respuesta a lo que Connect exige).

Se ejecuta como servidor HTTP (``app.run()``, puerto 8080 por convencion del
SDK de AgentCore) dentro del contenedor que construye
`scripts/deploy_agentcore.ps1` via el `bedrock-agentcore-starter-toolkit`
(build remoto en CodeBuild, sin Docker local).
"""

import logging
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

logging.basicConfig(level=logging.INFO)
# Mismo fix defensivo que el resto del repo aplica en Lambda (ver
# ../context.md, gotcha #1) -- acá el runtime no es Lambda así que
# basicConfig() alcanza, pero se deja el setLevel explícito por consistencia
# y porque no hace daño.
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)

from core.turn_service import process_turn  # noqa: E402

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict[str, Any], context: Any = None) -> dict[str, Any]:
    payload = payload or {}
    conversation_id = payload.get("conversation_id") or payload.get("contact_id")
    message = payload.get("message", "")
    return process_turn(conversation_id, message)


if __name__ == "__main__":
    app.run()
