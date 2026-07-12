from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_region: str = "us-east-1"
    dynamodb_table_name: str = "ConversationSessions"
    connect_instance_id: str
    connect_contact_flow_id: str
    chat_events_topic_arn: str
    telegram_secret_name: str = "telegram-inbound-adapter/telegram-bot"

    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None

    session_ttl_seconds: int = 60 * 60 * 6


@lru_cache
def get_settings() -> Settings:
    return Settings()
