from typing import Literal, TypedDict

# Debe coincidir con los valores que ya esperan los contact flows de Connect
# (activeIntent en telegram-inbound-adapter/scripts/provision_connect_flows.py).
# "atencion" ya no es una intencion clasificable -- ver graph.py: saludos y
# mensajes ambiguos ahora responden "ninguna" (fuera de VALID_INTENTS, mismo
# tratamiento que cualquier clasificacion inconclusa: intent=None) en vez de
# matchear un catch-all, para que F_Menu_Router/F_Menu_Reintento los manden
# al loop de reintento en vez de a una cola.
Intent = Literal["soporte", "ventas", "cobranza"]

VALID_INTENTS: frozenset[str] = frozenset({"soporte", "ventas", "cobranza"})


class IntentState(TypedDict):
    """Estado del grafo de LangGraph: entra con `message`, sale con `intent`
    (`None` si la clasificacion fue inconclusa o fallo)."""

    message: str
    intent: Intent | None
