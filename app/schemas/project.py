import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import BillingType, ProjectStatus


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    client_id: uuid.UUID | None = None
    status: ProjectStatus = ProjectStatus.PLANNING
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")
    billing_type: BillingType = BillingType.HOURLY
    hourly_rate: float | None = Field(default=None, ge=0)
    fixed_budget: float | None = Field(default=None, ge=0)
    start_date: date | None = None
    due_date: date | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    client_id: uuid.UUID | None = None
    status: ProjectStatus | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    billing_type: BillingType | None = None
    hourly_rate: float | None = Field(default=None, ge=0)
    fixed_budget: float | None = Field(default=None, ge=0)
    start_date: date | None = None
    due_date: date | None = None
    is_archived: bool | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    status: ProjectStatus
    client_id: uuid.UUID | None
    color: str
    billing_type: BillingType
    hourly_rate: float | None
    fixed_budget: float | None
    start_date: date | None
    due_date: date | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class ProjectWithStats(ProjectOut):
    client_name: str | None = None
    task_count: int = 0
    completed_task_count: int = 0
    total_hours_logged: float = 0
    total_billable_amount: float = 0
