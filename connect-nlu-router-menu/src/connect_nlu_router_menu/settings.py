from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_region: str = "us-east-1"

    # amazon.nova-micro-v1:0 es el modelo mas barato/rapido de Bedrock para
    # clasificacion de texto -- ver ../../context.md.
    nova_model_id: str = "amazon.nova-micro-v1:0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
