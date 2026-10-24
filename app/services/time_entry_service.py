import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.pagination import paginate
from app.models.project import Project
from app.models.time_entry import TimeEntry
from app.services import activity_service
from app.services.project_service import get_project


def _minutes_between(start: datetime, end: datetime) -> int:
    return max(1, round((end - start).total_seconds() / 60))


async def create_time_entry(db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: dict) -> TimeEntry:
    await get_project(db, tenant_id=tenant_id, project_id=data["project_id"])

    started_at = data["started_at"]
    ended_at = data.get("ended_at")
    duration = data.get("duration_minutes")

    # A manually logged duration is a completed time entry, not a running timer.
    # Timer state is represented by ended_at IS NULL, so keep the timestamps and
    # duration consistent for all manual-entry payload shapes.
    if ended_at is not None:
        duration = _minutes_between(started_at, ended_at)
    elif duration is not None:
        ended_at = started_at + timedelta(minutes=duration)

    entry = TimeEntry(
        tenant_id=tenant_id, user_id=user_id,
        project_id=data["project_id"], task_id=data.get("task_id"),
        description=data.get("description"), started_at=started_at, ended_at=ended_at,
        duration_minutes=duration, is_billable=data.get("is_billable", True),
    )
    db.add(entry)
    await db.flush()
    return entry


async def start_timer(db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: dict) -> TimeEntry:
    await get_project(db, tenant_id=tenant_id, project_id=data["project_id"])

    running = await get_running_timer(db, tenant_id=tenant_id, user_id=user_id)
    if running:
        raise ConflictError("You already have a running timer. Stop it before starting a new one.")

    entry = TimeEntry(
        tenant_id=tenant_id, user_id=user_id, project_id=data["project_id"], task_id=data.get("task_id"),
        description=data.get("description"), started_at=datetime.now(timezone.utc), is_billable=True,
    )
    db.add(entry)
    await db.flush()
    return entry


async def get_running_timer(db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> TimeEntry | None:
    result = await db.execute(
        select(TimeEntry).where(
            TimeEntry.tenant_id == tenant_id, TimeEntry.user_id == user_id, TimeEntry.ended_at.is_(None)
        )
    )
    return result.scalar_one_or_none()


async def stop_timer(db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> TimeEntry:
    entry = await get_running_timer(db, tenant_id=tenant_id, user_id=user_id)
    if not entry:
        raise NotFoundError("No running timer found.")
    entry.ended_at = datetime.now(timezone.utc)
    entry.duration_minutes = _minutes_between(entry.started_at, entry.ended_at)
    await db.flush()
    return entry


async def get_time_entry(db: AsyncSession, *, tenant_id: uuid.UUID, entry_id: uuid.UUID) -> TimeEntry:
    result = await db.execute(select(TimeEntry).where(TimeEntry.id == entry_id, TimeEntry.tenant_id == tenant_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise NotFoundError("Time entry not found.")
    return entry


async def list_time_entries(
    db: AsyncSession, *, tenant_id: uuid.UUID, project_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None, is_invoiced: bool | None = None,
    page: int = 1, page_size: int = 50,
) -> tuple[list[TimeEntry], int]:
    stmt = select(TimeEntry).where(TimeEntry.tenant_id == tenant_id)
    if project_id:
        stmt = stmt.where(TimeEntry.project_id == project_id)
    if user_id:
        stmt = stmt.where(TimeEntry.user_id == user_id)
    if is_invoiced is not None:
        stmt = stmt.where(TimeEntry.is_invoiced == is_invoiced)
    stmt = stmt.order_by(TimeEntry.started_at.desc())
    return await paginate(db, stmt, page=page, page_size=page_size)


async def update_time_entry(
    db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, entry_id: uuid.UUID, data: dict
) -> TimeEntry:
    entry = await get_time_entry(db, tenant_id=tenant_id, entry_id=entry_id)
    if entry.is_invoiced:
        raise ValidationError("This time entry has already been invoiced and can no longer be edited.")
    if entry.user_id != actor_id:
        raise ValidationError("You can only edit your own time entries.")

    for key, value in data.items():
        setattr(entry, key, value)
    if entry.ended_at and entry.started_at:
        entry.duration_minutes = _minutes_between(entry.started_at, entry.ended_at)
    await db.flush()
    return entry


async def delete_time_entry(db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, entry_id: uuid.UUID) -> None:
    entry = await get_time_entry(db, tenant_id=tenant_id, entry_id=entry_id)
    if entry.is_invoiced:
        raise ValidationError("This time entry has already been invoiced and cannot be deleted.")
    if entry.user_id != actor_id:
        raise ValidationError("You can only delete your own time entries.")
    await db.delete(entry)
    await db.flush()
