from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TelegramChat(BaseModel):
    id: int
    type: str


class TelegramFrom(BaseModel):
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class TelegramMessage(BaseModel):
    message_id: int
    chat: TelegramChat
    from_: TelegramFrom | None = Field(default=None, alias="from")
    text: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class TelegramUpdate(BaseModel):
    update_id: int
    message: TelegramMessage | None = None


class SessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


class SessionRecord(BaseModel):
    pk: str
    channel: str
    external_user_id: str
    connect_contact_id: str
    participant_id: str
    participant_token: str
    connection_token: str
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ttl: int

    @staticmethod
    def build_pk(channel: str, external_user_id: str) -> str:
        return f"{channel}#{external_user_id}"
