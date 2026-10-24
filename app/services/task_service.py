import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.pagination import paginate
from app.models.membership import Membership
from app.models.project import Project
from app.models.task import Task, TaskComment, TaskStatus
from app.services import activity_service, notification_service

KANBAN_COLUMN_ORDER = [
    TaskStatus.BACKLOG, TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.IN_REVIEW, TaskStatus.DONE,
]


async def _validate_project(db: AsyncSession, *, tenant_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id))
    project = result.scalar_one_or_none()
    if not project:
        raise ValidationError("The selected project does not exist in this workspace.")
    return project


async def _validate_assignee(db: AsyncSession, *, tenant_id: uuid.UUID, assignee_id: uuid.UUID | None) -> None:
    if assignee_id is None:
        return
    result = await db.execute(
        select(Membership).where(Membership.tenant_id == tenant_id, Membership.user_id == assignee_id)
    )
    if not result.scalar_one_or_none():
        raise ValidationError("Assignee must be a member of this workspace.")


async def _next_position(db: AsyncSession, *, tenant_id: uuid.UUID, project_id: uuid.UUID, status: TaskStatus) -> float:
    # Use advisory lock to prevent concurrent inserts from getting the same position.
    # This avoids the "FOR UPDATE not allowed with aggregate functions" error.
    lock_key = (hash((str(tenant_id), str(project_id), status.value)) & 0x7FFFFFFF)
    await db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    result = await db.execute(
        select(func.coalesce(func.max(Task.position), 0)).where(
            Task.tenant_id == tenant_id, Task.project_id == project_id, Task.status == status
        )
    )
    return float(result.scalar_one()) + 1024.0


async def create_task(db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, data: dict) -> Task:
    await _validate_project(db, tenant_id=tenant_id, project_id=data["project_id"])
    await _validate_assignee(db, tenant_id=tenant_id, assignee_id=data.get("assignee_id"))

    position = await _next_position(db, tenant_id=tenant_id, project_id=data["project_id"], status=data["status"])
    task = Task(tenant_id=tenant_id, position=position, **data)
    db.add(task)
    await db.flush()

    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action="task.created",
        entity_type="task", entity_id=task.id, entity_label=task.title,
    )
    if task.assignee_id and task.assignee_id != actor_id:
        await notification_service.notify_task_assigned(db, tenant_id=tenant_id, task=task)
    return task


async def get_task(db: AsyncSession, *, tenant_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id, Task.tenant_id == tenant_id))
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundError("Task not found.")
    return task


async def list_tasks(
    db: AsyncSession, *, tenant_id: uuid.UUID, project_id: uuid.UUID | None = None,
    status: TaskStatus | None = None, assignee_id: uuid.UUID | None = None,
    search: str | None = None, page: int = 1, page_size: int = 50,
) -> tuple[list[Task], int]:
    stmt = select(Task).where(Task.tenant_id == tenant_id)
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if status:
        stmt = stmt.where(Task.status == status)
    if assignee_id:
        stmt = stmt.where(Task.assignee_id == assignee_id)
    if search:
        stmt = stmt.where(func.lower(Task.title).like(f"%{search.lower()}%"))
    stmt = stmt.order_by(Task.status, Task.position)
    return await paginate(db, stmt, page=page, page_size=page_size)


async def get_kanban_board(db: AsyncSession, *, tenant_id: uuid.UUID, project_id: uuid.UUID) -> dict[TaskStatus, list[Task]]:
    from app.services.project_service import get_project

    await get_project(db, tenant_id=tenant_id, project_id=project_id)
    result = await db.execute(
        select(Task)
        .where(Task.tenant_id == tenant_id, Task.project_id == project_id)
        .order_by(Task.status, Task.position)
    )
    tasks = list(result.scalars().all())
    board: dict[TaskStatus, list[Task]] = {status: [] for status in KANBAN_COLUMN_ORDER}
    for task in tasks:
        board[task.status].append(task)
    return board


async def update_task(
    db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, task_id: uuid.UUID, data: dict
) -> Task:
    task = await get_task(db, tenant_id=tenant_id, task_id=task_id)
    if "assignee_id" in data:
        await _validate_assignee(db, tenant_id=tenant_id, assignee_id=data["assignee_id"])

    old_status = task.status
    old_assignee = task.assignee_id
    for key, value in data.items():
        setattr(task, key, value)

    if "status" in data:
        if data["status"] == TaskStatus.DONE and old_status != TaskStatus.DONE:
            task.completed_at = datetime.now(timezone.utc)
        elif data["status"] != TaskStatus.DONE:
            task.completed_at = None

    await db.flush()

    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action="task.updated",
        entity_type="task", entity_id=task.id, entity_label=task.title,
    )
    if "assignee_id" in data and task.assignee_id != old_assignee and task.assignee_id and task.assignee_id != actor_id:
        await notification_service.notify_task_assigned(db, tenant_id=tenant_id, task=task)
    return task


async def move_task(
    db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, task_id: uuid.UUID,
    new_status: TaskStatus, new_position: float,
) -> Task:
    """Dedicated Kanban drag-and-drop move: the frontend computes a
    fractional position between the two neighboring cards it was dropped
    between (or beyond the first/last), so reordering never requires
    renumbering every sibling row — an O(1) write regardless of column size.
    """
    return await update_task(
        db, tenant_id=tenant_id, actor_id=actor_id, task_id=task_id,
        data={"status": new_status, "position": new_position},
    )


async def delete_task(db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, task_id: uuid.UUID) -> None:
    task = await get_task(db, tenant_id=tenant_id, task_id=task_id)
    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action="task.deleted",
        entity_type="task", entity_id=task.id, entity_label=task.title,
    )
    await db.delete(task)
    await db.flush()


async def add_comment(
    db: AsyncSession, *, tenant_id: uuid.UUID, task_id: uuid.UUID, author_id: uuid.UUID, body: str
) -> TaskComment:
    task = await get_task(db, tenant_id=tenant_id, task_id=task_id)
    comment = TaskComment(tenant_id=tenant_id, task_id=task.id, author_id=author_id, body=body)
    db.add(comment)
    await db.flush()
    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=author_id, action="task.commented",
        entity_type="task", entity_id=task.id, entity_label=task.title,
    )
    return comment


async def list_comments(db: AsyncSession, *, tenant_id: uuid.UUID, task_id: uuid.UUID) -> list[TaskComment]:
    await get_task(db, tenant_id=tenant_id, task_id=task_id)
    result = await db.execute(
        select(TaskComment)
        .where(TaskComment.tenant_id == tenant_id, TaskComment.task_id == task_id)
        .order_by(TaskComment.created_at.asc())
    )
    return list(result.scalars().all())
