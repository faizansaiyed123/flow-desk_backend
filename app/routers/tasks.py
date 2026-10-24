import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext
from app.core.pagination import total_pages
from app.database import get_db
from app.dependencies import get_auth_context, require_role
from app.models.membership import MembershipRole
from app.models.task import TaskStatus
from app.schemas.common import MessageResponse, Page
from app.schemas.task import (
    KanbanBoard,
    KanbanColumn,
    TaskCommentCreate,
    TaskCommentOut,
    TaskCreate,
    TaskMove,
    TaskOut,
    TaskUpdate,
)
from app.services import task_service

router = APIRouter()


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    payload: TaskCreate,
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    task = await task_service.create_task(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, data=payload.model_dump())
    return TaskOut.model_validate(task)


@router.get("", response_model=Page[TaskOut])
async def list_tasks(
    project_id: uuid.UUID | None = None,
    status: TaskStatus | None = None,
    assignee_id: uuid.UUID | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    items, total = await task_service.list_tasks(
        db, tenant_id=ctx.tenant_id, project_id=project_id, status=status, assignee_id=assignee_id,
        search=search, page=page, page_size=page_size,
    )
    return Page(
        items=[TaskOut.model_validate(t) for t in items],
        total=total, page=page, page_size=page_size, total_pages=total_pages(total, page_size),
    )


@router.get("/board/{project_id}", response_model=KanbanBoard)
async def get_kanban_board(
    project_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)
):
    board = await task_service.get_kanban_board(db, tenant_id=ctx.tenant_id, project_id=project_id)
    return KanbanBoard(
        columns=[
            KanbanColumn(status=status, tasks=[TaskOut.model_validate(t) for t in tasks])
            for status, tasks in board.items()
        ]
    )


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)):
    task = await task_service.get_task(db, tenant_id=ctx.tenant_id, task_id=task_id)
    return TaskOut.model_validate(task)


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    task = await task_service.update_task(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, task_id=task_id,
        data=payload.model_dump(exclude_unset=True),
    )
    return TaskOut.model_validate(task)


@router.patch("/{task_id}/move", response_model=TaskOut)
async def move_task(
    task_id: uuid.UUID,
    payload: TaskMove,
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    task = await task_service.move_task(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, task_id=task_id,
        new_status=payload.status, new_position=payload.position,
    )
    return TaskOut.model_validate(task)


@router.delete("/{task_id}", response_model=MessageResponse)
async def delete_task(
    task_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    await task_service.delete_task(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, task_id=task_id)
    return MessageResponse(message="Task deleted.")


@router.post("/{task_id}/comments", response_model=TaskCommentOut, status_code=201)
async def add_comment(
    task_id: uuid.UUID,
    payload: TaskCommentCreate,
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    comment = await task_service.add_comment(
        db, tenant_id=ctx.tenant_id, task_id=task_id, author_id=ctx.user.id, body=payload.body
    )
    return TaskCommentOut.model_validate(comment)


@router.get("/{task_id}/comments", response_model=list[TaskCommentOut])
async def list_comments(
    task_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)
):
    comments = await task_service.list_comments(db, tenant_id=ctx.tenant_id, task_id=task_id)
    return [TaskCommentOut.model_validate(c) for c in comments]
