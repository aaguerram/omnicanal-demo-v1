import os
import json
from typing import Dict, Any
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from langchain_google_vertexai import ChatVertexAI
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from core.state import AgentState

load_dotenv()

class UpdatePatientInfo(BaseModel):
    """Actualiza la información médica y de síntomas del paciente."""
    acne_level: str = Field(description="Nivel de acné: leve, moderado, severo, ninguno", default=None)
    skin_type: str = Field(description="Tipo de piel: grasa, seca, mixta, normal", default=None)
    irritation: str = Field(description="Descripción de irritación o rojeces", default=None)
    allergies: str = Field(description="Alergias a ingredientes", default=None)

def diagnostico_node(state: AgentState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    patient_info = state.get("patient_info", {})
    
    llm = ChatVertexAI(
        model="gemini-2.5-flash-lite", 
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "skincare-ai-commerce"),
        temperature=0.5
    )
    
    llm_with_tools = llm.bind_tools([UpdatePatientInfo])
    
    system_prompt = f"""
Soy Luna, asesora virtual de cuidado de la piel. Hablo en español con un tono amigable y profesional, usando "tú".

Mi objetivo en esta conversación es conocer mejor tu piel para darte recomendaciones precisas.
Necesito entender 4 aspectos: el nivel de acné que presentas (leve, moderado, severo o ninguno), tu tipo de piel (grasa, seca, mixta o normal), si tienes alguna irritación o rojeces, y si tienes alergias a alguno ingrediente.

Información que ya tengo sobre ti: {json.dumps(patient_info, ensure_ascii=False)}

Cómo me comporto:
- Hago 1 o 2 preguntas por turno para no agobiarte.
- Si ya recopilé toda la información, te doy un breve resumen y te cuento que puedo buscarte productos recomendados.
- Si adjuntaste una foto, deduzco visualmente lo que veo (rojeces, granitos) y te pregunto si es correcto.
- Guardo cualquier dato nuevo que me cuentes durante la conversación.

Ejemplo de respuesta esperada:
"Cuento con que me cuentes un poco más sobre tu piel. ¿La sientes seca, grasa o mixta?"
    """
    
    response = llm_with_tools.invoke([SystemMessage(content=system_prompt)] + messages)
    
    updates = {"messages": [response]}
    
    # Handle tool calls manually to update state
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tool_call in response.tool_calls:
            if tool_call['name'] == 'UpdatePatientInfo':
                args = tool_call['args']
                new_info = patient_info.copy()
                for k, v in args.items():
                    if v is not None:
                        new_info[k] = v
                updates["patient_info"] = new_info
                
                # Add a tool message to satisfy Langchain/LangGraph requirements
                tool_msg = ToolMessage(
                    content=f"Información actualizada: {args}",
                    tool_call_id=tool_call['id']
                )
                updates["messages"].append(tool_msg)
                
                # Optionally, invoke LLM again to generate a response based on the updated info
                # For simplicity, we just return the tool call and the ToolMessage.
                # The user will see the LLM's text (if any) or we can generate a follow-up.
                
    return updates
