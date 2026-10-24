import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext
from app.database import get_db
from app.dependencies import require_role
from app.models.membership import MembershipRole
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreatedOut, ApiKeyOut
from app.schemas.common import MessageResponse
from app.services import api_key_service

router = APIRouter()


@router.post("", response_model=ApiKeyCreatedOut, status_code=201)
async def create_api_key(
    payload: ApiKeyCreate,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    api_key, plaintext_key = await api_key_service.create_api_key(
        db, tenant_id=ctx.tenant_id, created_by_id=ctx.user.id, name=payload.name
    )
    return ApiKeyCreatedOut(**ApiKeyOut.model_validate(api_key).model_dump(), plaintext_key=plaintext_key)


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)), db: AsyncSession = Depends(get_db)):
    keys = await api_key_service.list_api_keys(db, tenant_id=ctx.tenant_id)
    return [ApiKeyOut.model_validate(k) for k in keys]


@router.delete("/{api_key_id}", response_model=MessageResponse)
async def revoke_api_key(
    api_key_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    await api_key_service.revoke_api_key(db, tenant_id=ctx.tenant_id, api_key_id=api_key_id)
    return MessageResponse(message="API key revoked.")
