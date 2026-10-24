import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.webhook import WebhookEvent

VALID_EVENTS = {e.value for e in WebhookEvent}


class WebhookCreate(BaseModel):
    target_url: str = Field(min_length=1, max_length=500)
    events: list[str] = Field(min_length=1)
    description: str | None = Field(default=None, max_length=200)

    @field_validator("target_url")
    @classmethod
    def must_be_https_or_http(cls, v: str) -> str:
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("target_url must be a valid http(s) URL.")
        return v

    @field_validator("events")
    @classmethod
    def events_must_be_known(cls, v: list[str]) -> list[str]:
        unknown = set(v) - VALID_EVENTS
        if unknown:
            raise ValueError(f"Unknown event(s): {', '.join(sorted(unknown))}")
        return v


class WebhookUpdate(BaseModel):
    target_url: str | None = None
    events: list[str] | None = None
    description: str | None = None
    is_active: bool | None = None


class WebhookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target_url: str
    events: list[str]
    description: str | None
    is_active: bool
    created_at: datetime


class WebhookCreatedOut(WebhookOut):
    secret: str  # only ever returned once, at creation time


class WebhookDeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event: str
    response_status: int | None
    success: bool
    attempted_at: datetime
