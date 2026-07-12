from langgraph.graph import StateGraph, END
from core.state import AgentState
from core.router import route_message
from features.diagnostico_sintomas.graph import diagnostico_node
from features.info_productos.graph import info_productos_node

def build_graph():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("diagnostico_sintomas", diagnostico_node)
    workflow.add_node("info_productos", info_productos_node)
    
    # Usamos un conditional edge desde el inicio para enrutar el mensaje
    workflow.set_conditional_entry_point(
        route_message,
        {
            "diagnostico_sintomas": "diagnostico_sintomas",
            "info_productos": "info_productos"
        }
    )
    
    # Al finalizar el nodo, termina la ejecución del grafo por este turno
    workflow.add_edge("diagnostico_sintomas", END)
    workflow.add_edge("info_productos", END)
    
    return workflow.compile()

app_graph = build_graph()
