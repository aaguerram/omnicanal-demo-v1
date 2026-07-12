from typing import Literal
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_vertexai import ChatVertexAI
from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv
from core.state import AgentState

load_dotenv()

class RouterResponse(BaseModel):
    next_node: Literal["diagnostico_sintomas", "info_productos"] = Field(
        description="Enruta a 'diagnostico_sintomas' si el usuario describe un problema de la piel, adjunta una foto para analizar, o habla de síntomas. Enruta a 'info_productos' si pregunta directamente sobre ingredientes, modo de uso o detalles de productos en particular."
    )

def route_message(state: AgentState) -> Literal["diagnostico_sintomas", "info_productos"]:
    messages = state.get("messages", [])
    if not messages:
        return "diagnostico_sintomas"
        
    llm = ChatVertexAI(
        model="gemini-2.5-flash-lite", 
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "skincare-ai-commerce"),
        temperature=0.0
    )
    
    structured_llm = llm.with_structured_output(RouterResponse)
    
    system_prompt = SystemMessage(content="""
Soy el enrutador del asistente de skincare. Mi función es decidir cuál subsistema debe atender cada mensaje del usuario.

Cuando el usuario describe un problema en su piel, menciona síntomas como acné, irritación o alergias, o adjunta una foto para analizarla, envío la solicitud al subsistema de diagnóstico de síntomas.

Cuando el usuario pregunta directamente sobre un producto específico, sus ingredientes activos, modo de uso, precio o disponibilidad, envío la solicitud al subsistema de información de productos.

Si el mensaje es ambiguo, opto por el subsistema de diagnóstico de síntomas.
    """)
    
    try:
        # We only need the last message and the system prompt for routing
        response = structured_llm.invoke([system_prompt, messages[-1]])
        return response.next_node
    except Exception as e:
        print(f"Error in router: {e}")
        return "diagnostico_sintomas"
