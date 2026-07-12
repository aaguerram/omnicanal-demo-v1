from enum import StrEnum

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ConnectStreamingMessage(BaseModel):
    contact_id: str = Field(validation_alias=AliasChoices("ContactId", "InitialContactId"))
    participant_role: str | None = Field(default=None, alias="ParticipantRole")
    type: str | None = Field(default=None, alias="Type")
    content: str | None = Field(default=None, alias="Content")
    content_type: str | None = Field(default=None, alias="ContentType")

    model_config = ConfigDict(populate_by_name=True)


class SessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
