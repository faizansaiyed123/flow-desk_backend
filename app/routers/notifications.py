import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext
from app.core.pagination import total_pages
from app.database import get_db
from app.dependencies import get_auth_context
from app.schemas.common import MessageResponse, Page
from app.schemas.notification import NotificationOut, UnreadCountOut
from app.services import notification_service

router = APIRouter()


@router.get("", response_model=Page[NotificationOut])
async def list_notifications(
    unread_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    items, total = await notification_service.list_notifications(
        db, tenant_id=ctx.tenant_id, user_id=ctx.user.id, unread_only=unread_only, page=page, page_size=page_size,
    )
    return Page(
        items=[NotificationOut.model_validate(n) for n in items],
        total=total, page=page, page_size=page_size, total_pages=total_pages(total, page_size),
    )


@router.get("/unread-count", response_model=UnreadCountOut)
async def get_unread_count(ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)):
    count = await notification_service.unread_count(db, tenant_id=ctx.tenant_id, user_id=ctx.user.id)
    return UnreadCountOut(count=count)


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)
):
    notification = await notification_service.mark_read(
        db, tenant_id=ctx.tenant_id, user_id=ctx.user.id, notification_id=notification_id
    )
    return NotificationOut.model_validate(notification)


@router.post("/read-all", response_model=MessageResponse)
async def mark_all_read(ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)):
    await notification_service.mark_all_read(db, tenant_id=ctx.tenant_id, user_id=ctx.user.id)
    return MessageResponse(message="All notifications marked as read.")
