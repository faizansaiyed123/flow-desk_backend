import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TimeEntryCreate(BaseModel):
    project_id: uuid.UUID
    task_id: uuid.UUID | None = None
    description: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1)
    is_billable: bool = True

    @model_validator(mode="after")
    def _require_end_or_duration(self):
        if self.ended_at is None and self.duration_minutes is None:
            raise ValueError("Either ended_at or duration_minutes must be provided.")
        if self.ended_at is not None and self.ended_at <= self.started_at:
            raise ValueError("ended_at must be after started_at.")
        return self


class TimeEntryUpdate(BaseModel):
    description: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1)
    is_billable: bool | None = None


class TimerStartRequest(BaseModel):
    project_id: uuid.UUID
    task_id: uuid.UUID | None = None
    description: str | None = None


class TimeEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None
    user_id: uuid.UUID
    description: str | None
    started_at: datetime
    ended_at: datetime | None
    duration_minutes: int | None
    is_billable: bool
    is_invoiced: bool
    created_at: datetime
