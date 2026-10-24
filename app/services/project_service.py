import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.pagination import paginate
from app.models.client import Client
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.time_entry import TimeEntry
from app.services import activity_service


async def _validate_client(db: AsyncSession, *, tenant_id: uuid.UUID, client_id: uuid.UUID | None) -> None:
    if client_id is None:
        return
    result = await db.execute(select(Client).where(Client.id == client_id, Client.tenant_id == tenant_id))
    if not result.scalar_one_or_none():
        raise ValidationError("The selected client does not exist in this workspace.")


async def create_project(db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, data: dict) -> Project:
    await _validate_client(db, tenant_id=tenant_id, client_id=data.get("client_id"))
    project = Project(tenant_id=tenant_id, **data)
    db.add(project)
    await db.flush()
    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action="project.created",
        entity_type="project", entity_id=project.id, entity_label=project.name,
    )
    return project


async def get_project(db: AsyncSession, *, tenant_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id))
    project = result.scalar_one_or_none()
    if not project:
        raise NotFoundError("Project not found.")
    return project


async def list_projects(
    db: AsyncSession, *, tenant_id: uuid.UUID, search: str | None = None, status: ProjectStatus | None = None,
    client_id: uuid.UUID | None = None, include_archived: bool = False, page: int = 1, page_size: int = 20,
) -> tuple[list[Project], int]:
    stmt = select(Project).where(Project.tenant_id == tenant_id)
    if not include_archived:
        stmt = stmt.where(Project.is_archived.is_(False))
    if search:
        stmt = stmt.where(func.lower(Project.name).like(f"%{search.lower()}%"))
    if status:
        stmt = stmt.where(Project.status == status)
    if client_id:
        stmt = stmt.where(Project.client_id == client_id)
    stmt = stmt.order_by(Project.created_at.desc())
    return await paginate(db, stmt, page=page, page_size=page_size)


async def update_project(
    db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, project_id: uuid.UUID, data: dict
) -> Project:
    project = await get_project(db, tenant_id=tenant_id, project_id=project_id)
    if "client_id" in data:
        await _validate_client(db, tenant_id=tenant_id, client_id=data["client_id"])

    old_status = project.status
    for key, value in data.items():
        setattr(project, key, value)
    await db.flush()

    action = "project.updated"
    if "status" in data and data["status"] != old_status:
        action = "project.status_changed"
    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action=action,
        entity_type="project", entity_id=project.id, entity_label=project.name,
        metadata={"old_status": old_status.value, "new_status": project.status.value} if action == "project.status_changed" else None,
    )
    return project


async def delete_project(db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, project_id: uuid.UUID) -> None:
    project = await get_project(db, tenant_id=tenant_id, project_id=project_id)
    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action="project.deleted",
        entity_type="project", entity_id=project.id, entity_label=project.name,
    )
    await db.delete(project)
    await db.flush()


async def get_project_stats(db: AsyncSession, *, tenant_id: uuid.UUID, project_id: uuid.UUID) -> dict:
    task_count = (
        await db.execute(select(func.count()).where(Task.tenant_id == tenant_id, Task.project_id == project_id))
    ).scalar_one()
    completed_task_count = (
        await db.execute(
            select(func.count()).where(
                Task.tenant_id == tenant_id, Task.project_id == project_id, Task.status == TaskStatus.DONE
            )
        )
    ).scalar_one()
    total_minutes = (
        await db.execute(
            select(func.coalesce(func.sum(TimeEntry.duration_minutes), 0)).where(
                TimeEntry.tenant_id == tenant_id, TimeEntry.project_id == project_id
            )
        )
    ).scalar_one()
    billable_minutes = (
        await db.execute(
            select(func.coalesce(func.sum(TimeEntry.duration_minutes), 0)).where(
                TimeEntry.tenant_id == tenant_id, TimeEntry.project_id == project_id,
                TimeEntry.is_billable.is_(True),
            )
        )
    ).scalar_one()

    project = await get_project(db, tenant_id=tenant_id, project_id=project_id)
    hourly_rate = float(project.hourly_rate) if project.hourly_rate else 0.0
    total_billable_amount = (float(billable_minutes) / 60.0) * hourly_rate

    client_name = None
    if project.client_id:
        client = await db.get(Client, project.client_id)
        client_name = client.name if client else None

    return {
        "task_count": task_count,
        "completed_task_count": completed_task_count,
        "total_hours_logged": round(float(total_minutes) / 60.0, 2),
        "total_billable_amount": round(total_billable_amount, 2),
        "client_name": client_name,
    }
