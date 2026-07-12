from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_region: str = "us-east-1"
    dynamodb_table_name: str = "SkincareAgentSessions"

    # Modelo de Bedrock para todos los nodos que usan LLM (router, estado_turno,
    # diagnostico_sintomas, info_productos) -- mismo modelo e integracion
    # (ChatBedrockConverse via langchain-aws) que connect-nlu-router-menu, ver
    # ../context.md.
    nova_model_id: str = "amazon.nova-micro-v1:0"
    # Modelo de embeddings de Bedrock para el RAG de info_productos
    # (FirestoreVectorStore) -- ver features/info_productos/graph.py y
    # scripts/ingestar_pdfs.py.
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"

    google_cloud_project: str = "skincare-ai-commerce"
    # Secreto en Secrets Manager con el JSON de la service account de GCP
    # (solo Firestore -- el chat/embeddings ya no usan Vertex AI/Gemini). Ver
    # scripts/create_gcp_service_account.ps1 y scripts/provision.ps1.
    gcp_secret_name: str = "agentic-skincare-backend/gcp-service-account"

    session_ttl_seconds: int = 60 * 60 * 6
    # Cuantos turnos "no_resuelto" seguidos antes de escalar a un asesor
    # humano de ventas -- ver core/estado_turno.py y entrypoints/lambda_handler.py.
    max_consecutive_unresolved: int = 3
    # Tope de mensajes que se persisten en DynamoDB por conversacion, para no
    # hacer crecer el item ni el contexto que se manda al LLM sin limite.
    max_stored_messages: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()
