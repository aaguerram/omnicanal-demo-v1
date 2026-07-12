from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_region: str = "us-east-1"
    dynamodb_table_name: str = "ConversationSessions"
    telegram_secret_name: str = "telegram-inbound-adapter/telegram-bot"

    # Local-only override; in Lambda this comes from Secrets Manager instead.
    telegram_bot_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
