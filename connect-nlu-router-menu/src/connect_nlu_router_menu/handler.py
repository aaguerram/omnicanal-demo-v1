import logging
from typing import Any

from langchain_aws import ChatBedrockConverse
from langgraph.graph.state import CompiledStateGraph

from connect_nlu_router_menu.graph import build_graph
from connect_nlu_router_menu.settings import get_settings

logging.basicConfig(level=logging.INFO)
# Mismo fix que telegram-inbound-adapter/telegram-outbound-adapter: el runtime
# de Lambda le adjunta un handler al logger raiz antes de que corra este
# codigo, asi que basicConfig() es un no-op sin este setLevel explicito.
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)

_settings = get_settings()

# ChatBedrockConverse resuelve credenciales de AWS al construirse (a
# diferencia de un boto3.client() plano, que no valida nada hasta la primera
# llamada real) -- construirlo a nivel de modulo rompe cualquier import sin
# credenciales validas a mano (tests, `pip install -e .`, etc.), aunque el rol
# de ejecucion de Lambda si las tenga en cold start. Por eso el grafo se arma
# perezosamente en el primer invoke() real. Los tests monkeypatchean
# `_get_graph` directo -- ver tests/test_handler.py.
_graph_cache: CompiledStateGraph | None = None


def _get_graph() -> CompiledStateGraph:
    global _graph_cache
    if _graph_cache is None:
        llm = ChatBedrockConverse(
            model_id=_settings.nova_model_id,
            region_name=_settings.aws_region,
            temperature=0,
            max_tokens=10,
        )
        _graph_cache = build_graph(llm)
    return _graph_cache


def _extract_message(event: dict[str, Any] | None) -> str:
    """Dos formas de invocacion soportadas:

    1. Invocacion directa via boto3 (`lambda.invoke`, ver README.md):
       `event = {"message": "..."}`.
    2. Bloque "Invoke AWS Lambda function" de un contact flow de Amazon
       Connect (p. ej. F_Menu_Router): Connect envuelve los parametros
       configurados en el bloque (`LambdaInvocationAttributes`) dentro de
       `event["Details"]["Parameters"]`, junto con `ContactData` -- no manda
       `message` en el nivel superior.
    """
    event = event or {}
    details = event.get("Details")
    if isinstance(details, dict):
        return details.get("Parameters", {}).get("message", "")
    return event.get("message", "")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    # NOTE: igual que en los otros dos proyectos, nada de logger.info(msg,
    # extra={...}) -- el formatter por defecto solo renderiza %(message)s y
    # descarta `extra` en silencio. Todo lo que necesitamos ver va embebido
    # en el string del mensaje (f-string).
    message = _extract_message(event)
    logger.info(f"nlu_invocation_received message={message[:200]!r}")

    result = _get_graph().invoke({"message": message, "intent": None})
    intent = result.get("intent")

    logger.info(f"nlu_invocation_result intent={intent}")
    # Cuando este Lambda lo invoca un contact flow de Connect con
    # ResponseValidation=STRING_MAP, la respuesta debe ser un dict plano de
    # strings -- Connect rechaza `null`. "" reemplaza a None como valor de
    # "clasificacion inconclusa/fallo" (ver README.md, contrato actualizado).
    return {"intent": intent or ""}
