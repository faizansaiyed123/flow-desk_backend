import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext
from app.core.pagination import total_pages
from app.database import get_db
from app.dependencies import get_auth_context, require_role
from app.models.membership import MembershipRole
from app.schemas.common import MessageResponse, Page
from app.schemas.time_entry import TimeEntryCreate, TimeEntryOut, TimeEntryUpdate, TimerStartRequest
from app.services import time_entry_service

router = APIRouter()


@router.post("", response_model=TimeEntryOut, status_code=201)
async def create_time_entry(
    payload: TimeEntryCreate,
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    entry = await time_entry_service.create_time_entry(
        db, tenant_id=ctx.tenant_id, user_id=ctx.user.id, data=payload.model_dump()
    )
    return TimeEntryOut.model_validate(entry)


@router.post("/timer/start", response_model=TimeEntryOut, status_code=201)
async def start_timer(
    payload: TimerStartRequest,
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    entry = await time_entry_service.start_timer(db, tenant_id=ctx.tenant_id, user_id=ctx.user.id, data=payload.model_dump())
    return TimeEntryOut.model_validate(entry)


@router.post("/timer/stop", response_model=TimeEntryOut)
async def stop_timer(ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)):
    entry = await time_entry_service.stop_timer(db, tenant_id=ctx.tenant_id, user_id=ctx.user.id)
    return TimeEntryOut.model_validate(entry)


@router.get("/timer/running", response_model=TimeEntryOut | None)
async def get_running_timer(ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)):
    entry = await time_entry_service.get_running_timer(db, tenant_id=ctx.tenant_id, user_id=ctx.user.id)
    return TimeEntryOut.model_validate(entry) if entry else None


@router.get("", response_model=Page[TimeEntryOut])
async def list_time_entries(
    project_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    is_invoiced: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    items, total = await time_entry_service.list_time_entries(
        db, tenant_id=ctx.tenant_id, project_id=project_id, user_id=user_id, is_invoiced=is_invoiced,
        page=page, page_size=page_size,
    )
    return Page(
        items=[TimeEntryOut.model_validate(e) for e in items],
        total=total, page=page, page_size=page_size, total_pages=total_pages(total, page_size),
    )


@router.patch("/{entry_id}", response_model=TimeEntryOut)
async def update_time_entry(
    entry_id: uuid.UUID,
    payload: TimeEntryUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    entry = await time_entry_service.update_time_entry(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, entry_id=entry_id,
        data=payload.model_dump(exclude_unset=True),
    )
    return TimeEntryOut.model_validate(entry)


@router.delete("/{entry_id}", response_model=MessageResponse)
async def delete_time_entry(
    entry_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)
):
    await time_entry_service.delete_time_entry(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, entry_id=entry_id)
    return MessageResponse(message="Time entry deleted.")
