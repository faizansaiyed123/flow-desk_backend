import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import paginate
from app.models.notification import Notification, NotificationType
from app.models.task import Task


async def create_notification(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, type: NotificationType,
    title: str, body: str | None = None, link: str | None = None, metadata: dict | None = None,
) -> Notification:
    notification = Notification(
        tenant_id=tenant_id, user_id=user_id, type=type, title=title, body=body, link=link,
        metadata_json=metadata,
    )
    db.add(notification)
    await db.flush()
    return notification


async def notify_task_assigned(db: AsyncSession, *, tenant_id: uuid.UUID, task: Task) -> Notification:
    return await create_notification(
        db, tenant_id=tenant_id, user_id=task.assignee_id, type=NotificationType.TASK_ASSIGNED,
        title=f"You were assigned to \u201c{task.title}\u201d",
        link=f"/app/projects/{task.project_id}",
        metadata={"task_id": str(task.id), "project_id": str(task.project_id)},
    )


async def list_notifications(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, unread_only: bool = False,
    page: int = 1, page_size: int = 20,
) -> tuple[list[Notification], int]:
    stmt = select(Notification).where(Notification.tenant_id == tenant_id, Notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc())
    return await paginate(db, stmt, page=page, page_size=page_size)


async def unread_count(db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> int:
    from sqlalchemy import func

    result = await db.execute(
        select(func.count()).where(
            Notification.tenant_id == tenant_id, Notification.user_id == user_id, Notification.is_read.is_(False)
        )
    )
    return result.scalar_one()


async def mark_read(db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id, Notification.tenant_id == tenant_id, Notification.user_id == user_id
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise NotFoundError("Notification not found.")
    notification.is_read = True
    await db.flush()
    return notification


async def mark_all_read(db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.tenant_id == tenant_id, Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    await db.flush()
