import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskPriority, TaskStatus


class TaskCreate(BaseModel):
    project_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: uuid.UUID | None = None
    due_date: date | None = None
    estimated_hours: float | None = Field(default=None, ge=0)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee_id: uuid.UUID | None = None
    due_date: date | None = None
    estimated_hours: float | None = Field(default=None, ge=0)


class TaskMove(BaseModel):
    """Dedicated payload for Kanban drag-and-drop: change column (status)
    and/or position within the column in one atomic call."""

    status: TaskStatus
    position: float


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    assignee_id: uuid.UUID | None
    due_date: date | None
    position: float
    completed_at: datetime | None
    estimated_hours: float | None
    created_at: datetime
    updated_at: datetime


class TaskCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class TaskCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime


class KanbanColumn(BaseModel):
    status: TaskStatus
    tasks: list[TaskOut]


class KanbanBoard(BaseModel):
    columns: list[KanbanColumn]
