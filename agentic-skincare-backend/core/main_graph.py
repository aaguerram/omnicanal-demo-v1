from langgraph.graph import END, StateGraph

from core.estado_turno import evaluar_estado_node
from core.router import route_message
from core.state import AgentState
from features.diagnostico_sintomas.graph import diagnostico_node
from features.info_productos.graph import info_productos_node


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("diagnostico_sintomas", diagnostico_node)
    workflow.add_node("info_productos", info_productos_node)
    workflow.add_node("evaluar_estado", evaluar_estado_node)

    # Usamos un conditional edge desde el inicio para enrutar el mensaje
    workflow.set_conditional_entry_point(
        route_message,
        {
            "diagnostico_sintomas": "diagnostico_sintomas",
            "info_productos": "info_productos"
        }
    )

    # Ambas features pasan por evaluar_estado antes de terminar el turno --
    # ahi se decide turn_status (en_progreso/finalizado/no_resuelto), que
    # consume entrypoints/lambda_handler.py para el escalamiento a un asesor.
    workflow.add_edge("diagnostico_sintomas", "evaluar_estado")
    workflow.add_edge("info_productos", "evaluar_estado")
    workflow.add_edge("evaluar_estado", END)

    return workflow.compile()

app_graph = build_graph()
