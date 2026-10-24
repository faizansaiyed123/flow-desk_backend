import uuid
from datetime import date

from pydantic import BaseModel


class ProjectHealthOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    status: str
    task_count: int
    completed_task_count: int
    percent_complete: float
    due_date: date | None


class UpcomingTaskOut(BaseModel):
    id: uuid.UUID
    title: str
    project_id: uuid.UUID
    project_name: str
    due_date: date | None
    priority: str


class MonthlyRevenuePoint(BaseModel):
    month: str  # "2026-01"
    invoiced: float
    collected: float


class DashboardSummary(BaseModel):
    active_project_count: int
    total_client_count: int
    total_task_count: int
    overdue_task_count: int
    completed_tasks_last_7_days: int
    hours_logged_last_7_days: float
    outstanding_invoice_total: float
    paid_invoice_total_this_month: float
    project_health: list[ProjectHealthOut]
    upcoming_tasks: list[UpcomingTaskOut]
    revenue_by_month: list[MonthlyRevenuePoint]
