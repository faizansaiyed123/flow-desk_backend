import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.invoice import Invoice, InvoiceStatus
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.time_entry import TimeEntry


async def get_summary(db: AsyncSession, *, tenant_id: uuid.UUID) -> dict:
    now = datetime.now(timezone.utc)
    today = now.date()
    seven_days_ago = now - timedelta(days=7)
    month_start = today.replace(day=1)

    active_project_count = (
        await db.execute(
            select(func.count()).where(Project.tenant_id == tenant_id, Project.status == ProjectStatus.ACTIVE)
        )
    ).scalar_one()
    total_client_count = (
        await db.execute(
            select(func.count()).where(Client.tenant_id == tenant_id, Client.is_archived.is_(False))
        )
    ).scalar_one()
    total_task_count = (
        await db.execute(select(func.count()).where(Task.tenant_id == tenant_id))
    ).scalar_one()
    overdue_task_count = (
        await db.execute(
            select(func.count()).where(
                Task.tenant_id == tenant_id, Task.status != TaskStatus.DONE,
                Task.due_date.is_not(None), Task.due_date < today,
            )
        )
    ).scalar_one()
    completed_tasks_last_7_days = (
        await db.execute(
            select(func.count()).where(
                Task.tenant_id == tenant_id, Task.completed_at.is_not(None), Task.completed_at >= seven_days_ago
            )
        )
    ).scalar_one()
    minutes_last_7_days = (
        await db.execute(
            select(func.coalesce(func.sum(TimeEntry.duration_minutes), 0)).where(
                TimeEntry.tenant_id == tenant_id, TimeEntry.started_at >= seven_days_ago
            )
        )
    ).scalar_one()
    outstanding_invoice_total = (
        await db.execute(
            select(func.coalesce(func.sum(Invoice.total), 0)).where(
                Invoice.tenant_id == tenant_id, Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.OVERDUE])
            )
        )
    ).scalar_one()
    paid_invoice_total_this_month = (
        await db.execute(
            select(func.coalesce(func.sum(Invoice.total), 0)).where(
                Invoice.tenant_id == tenant_id, Invoice.status == InvoiceStatus.PAID,
                Invoice.paid_at >= month_start,
            )
        )
    ).scalar_one()

    projects_result = await db.execute(
        select(Project).where(Project.tenant_id == tenant_id, Project.status == ProjectStatus.ACTIVE)
        .order_by(Project.due_date.asc().nulls_last())
        .limit(10)
    )
    project_health = []
    for project in projects_result.scalars().all():
        counts = await db.execute(
            select(
                func.count(),
                func.sum(case((Task.status == TaskStatus.DONE, 1), else_=0)),
            ).where(Task.tenant_id == tenant_id, Task.project_id == project.id)
        )
        total, done = counts.one()
        total = total or 0
        done = done or 0
        project_health.append({
            "id": project.id, "name": project.name, "color": project.color, "status": project.status.value,
            "task_count": total, "completed_task_count": done,
            "percent_complete": round((done / total) * 100, 1) if total else 0.0,
            "due_date": project.due_date,
        })

    upcoming_result = await db.execute(
        select(Task, Project.name)
        .join(Project, Project.id == Task.project_id)
        .where(Task.tenant_id == tenant_id, Task.status != TaskStatus.DONE, Task.due_date.is_not(None))
        .order_by(Task.due_date.asc())
        .limit(8)
    )
    upcoming_tasks = [
        {
            "id": t.id, "title": t.title, "project_id": t.project_id, "project_name": pname,
            "due_date": t.due_date, "priority": t.priority.value,
        }
        for t, pname in upcoming_result.all()
    ]

    # Revenue by month for the last 6 months (invoiced vs collected).
    months = []
    cursor = today.replace(day=1)
    for _ in range(6):
        months.append(cursor)
        prev_month = cursor.month - 1 or 12
        prev_year = cursor.year - 1 if cursor.month == 1 else cursor.year
        cursor = date(prev_year, prev_month, 1)
    months.reverse()

    revenue_by_month = []
    for month_date in months:
        if month_date.month == 12:
            next_month = date(month_date.year + 1, 1, 1)
        else:
            next_month = date(month_date.year, month_date.month + 1, 1)

        invoiced = (
            await db.execute(
                select(func.coalesce(func.sum(Invoice.total), 0)).where(
                    Invoice.tenant_id == tenant_id, Invoice.status != InvoiceStatus.VOID,
                    Invoice.issue_date >= month_date, Invoice.issue_date < next_month,
                )
            )
        ).scalar_one()
        collected = (
            await db.execute(
                select(func.coalesce(func.sum(Invoice.total), 0)).where(
                    Invoice.tenant_id == tenant_id, Invoice.status == InvoiceStatus.PAID,
                    Invoice.paid_at >= month_date, Invoice.paid_at < next_month,
                )
            )
        ).scalar_one()
        revenue_by_month.append({
            "month": month_date.strftime("%Y-%m"), "invoiced": float(invoiced), "collected": float(collected),
        })

    return {
        "active_project_count": active_project_count,
        "total_client_count": total_client_count,
        "total_task_count": total_task_count,
        "overdue_task_count": overdue_task_count,
        "completed_tasks_last_7_days": completed_tasks_last_7_days,
        "hours_logged_last_7_days": round(float(minutes_last_7_days) / 60.0, 2),
        "outstanding_invoice_total": float(outstanding_invoice_total),
        "paid_invoice_total_this_month": float(paid_invoice_total_this_month),
        "project_health": project_health,
        "upcoming_tasks": upcoming_tasks,
        "revenue_by_month": revenue_by_month,
    }
