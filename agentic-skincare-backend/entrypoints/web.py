import os
import sys
import base64
from dotenv import load_dotenv
import gradio as gr
from langchain_core.messages import HumanMessage, AIMessage

# Asegurar que el directorio raíz está en el PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from core.main_graph import app_graph

load_dotenv()

# Almacenamiento simple en memoria para la información del paciente
session_store = {}

def predict(message, history):
    text = message.get("text", "")
    files = message.get("files", [])
    
    messages = []
    # En Gradio 6.x con type="messages", history es una lista de diccionarios/objetos Message:
    # [{"role": "user", "content": "text"}, {"role": "assistant", "content": "text"}]
    for msg in history:
        # Si history tiene un formato de lista de dicts (el estándar en Gradio 5/6)
        if isinstance(msg, dict):
            role = msg.get("role")
            content_val = msg.get("content")
            if role == "user":
                messages.append(HumanMessage(content=content_val))
            elif role == "assistant":
                messages.append(AIMessage(content=content_val))
        # O por si acaso viene como tupla en alguna versión/configuración
        elif isinstance(msg, (list, tuple)) and len(msg) == 2:
            user_msg, bot_msg = msg
            if isinstance(user_msg, tuple):
                messages.append(HumanMessage(content="[Imagen adjunta]"))
            elif isinstance(user_msg, str):
                messages.append(HumanMessage(content=user_msg))
            if bot_msg:
                messages.append(AIMessage(content=bot_msg))
            
    content = []
    if text:
        content.append({"type": "text", "text": text})
    else:
        content.append({"type": "text", "text": "Por favor, analiza la imagen adjunta."})
        
    if files:
        file_path = files[0]
        try:
            with open(file_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded_string}"}})
        except Exception as e:
            print(f"Error procesando imagen: {e}")
            
    messages.append(HumanMessage(content=content))
    
    initial_state = {
        "messages": messages,
        "patient_info": session_store.get("patient_info", {})
    }
    
    try:
        result = app_graph.invoke(initial_state)
        # Actualizar info del paciente en la "sesión"
        session_store["patient_info"] = result.get("patient_info", {})
        
        # El último mensaje siempre será la respuesta del bot
        return result["messages"][-1].content
    except Exception as e:
        print(f"Error executing graph: {e}")
        return "Hubo un error procesando tu solicitud. Por favor intenta nuevamente."

demo = gr.ChatInterface(
    fn=predict,
    multimodal=True,
    title="Skincare AI Assistant",
    description="Asistente experto en cuidado de la piel. Adjunta una foto o cuéntame tus síntomas para un diagnóstico, o pregúntame directamente por productos.",
)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
