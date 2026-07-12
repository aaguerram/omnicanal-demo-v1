import os
from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv
from core.settings import get_settings
from core.state import AgentState
from langchain_aws import BedrockEmbeddings, ChatBedrockConverse
from langchain_google_firestore import FirestoreVectorStore
from google.cloud import firestore

load_dotenv()

def info_productos_node(state: AgentState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    if not messages:
        return {"messages": []}
        
    last_message = messages[-1].content
    query_text = ""
    if isinstance(last_message, str):
        query_text = last_message
    elif isinstance(last_message, list):
        parts = []
        for part in last_message:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
            elif isinstance(part, str):
                parts.append(part)
        query_text = " ".join(parts)
    
    settings = get_settings()
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", settings.google_cloud_project)

    llm = ChatBedrockConverse(
        model_id=settings.nova_model_id,
        region_name=settings.aws_region,
        temperature=0.0,
        max_tokens=1470,
    )

    embeddings = BedrockEmbeddings(
        model_id=settings.bedrock_embedding_model_id,
        region_name=settings.aws_region,
    )
    
    try:
        # Initialize Firestore Client and Vector Store
        # Note: In production, it's better to reuse the client instance
        db = firestore.Client(project=project_id)
        vector_store = FirestoreVectorStore(
            collection="catalogo_productos",
            embedding_service=embeddings,
            client=db
        )
        
        # Perform similarity search
        docs = vector_store.similarity_search(query_text, k=3)
        context = "\n\n".join([doc.page_content for doc in docs])
    except Exception as e:
        print(f"Error accessing Firestore Vector Store: {e}")
        context = "No se pudo acceder a la base de datos de productos en este momento."
    
    system_prompt = f"""
Soy Luna, asesora virtual de cuidado de la piel. Hablo en español con un tono amigable y profesional, usando "tú".

Mi función en esta conversación es responder preguntas sobre productos específicos basándome únicamente en la información de los manuales y catálogos disponibles.

Información de productos disponible:
{context}

Cómo me comporto:
- Solo uso la información del catálogo. Si el dato que buscas no está disponible, te lo hago saber amablemente.
- No invento ingredientes, precios ni propiedades.
- Cuando menciono precios, uso el símbolo $ seguido del número (ejemplo: $45).
- Al terminar mi respuesta, te pregunto si quieres saber algo más sobre ese producto o si te interesa ver otras opciones.

Ejemplo de respuesta esperada:
"Este producto contiene niacinamida al 10% y zinc PCA. Es ideal para pieles grasas o con acné leve. ¿Te gustaría saber cómo aplicarlo o ver otras opciones similares?"
    """
    
    response = llm.invoke([SystemMessage(content=system_prompt)] + messages)
    
    return {"messages": [response]}
