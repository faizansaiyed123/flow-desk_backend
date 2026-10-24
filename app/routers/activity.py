import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext
from app.database import get_db
from app.dependencies import get_auth_context
from app.schemas.activity import ActivityLogOut
from app.services import activity_service

router = APIRouter()


@router.get("", response_model=list[ActivityLogOut])
async def list_activity(
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    logs = await activity_service.list_activity(
        db, tenant_id=ctx.tenant_id, limit=limit, offset=offset, entity_type=entity_type, entity_id=entity_id
    )
    return [ActivityLogOut.model_validate(log) for log in logs]
