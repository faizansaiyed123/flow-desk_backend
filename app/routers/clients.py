import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext
from app.core.pagination import total_pages
from app.database import get_db
from app.dependencies import get_auth_context, require_role
from app.models.membership import MembershipRole
from app.schemas.client import ClientCreate, ClientOut, ClientUpdate, ClientWithStats
from app.schemas.common import MessageResponse, Page
from app.services import client_service

router = APIRouter()


@router.post("", response_model=ClientOut, status_code=201)
async def create_client(
    payload: ClientCreate,
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    client = await client_service.create_client(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, data=payload.model_dump()
    )
    return ClientOut.model_validate(client)


@router.get("", response_model=Page[ClientOut])
async def list_clients(
    search: str | None = None,
    include_archived: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    items, total = await client_service.list_clients(
        db, tenant_id=ctx.tenant_id, search=search, include_archived=include_archived,
        page=page, page_size=page_size,
    )
    return Page(
        items=[ClientOut.model_validate(c) for c in items],
        total=total, page=page, page_size=page_size, total_pages=total_pages(total, page_size),
    )


@router.get("/{client_id}", response_model=ClientWithStats)
async def get_client(
    client_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)
):
    client = await client_service.get_client(db, tenant_id=ctx.tenant_id, client_id=client_id)
    stats = await client_service.get_client_stats(db, tenant_id=ctx.tenant_id, client_id=client_id)
    return ClientWithStats(**ClientOut.model_validate(client).model_dump(), **stats)


@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    client = await client_service.update_client(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, client_id=client_id,
        data=payload.model_dump(exclude_unset=True),
    )
    return ClientOut.model_validate(client)


@router.delete("/{client_id}", response_model=MessageResponse)
async def delete_client(
    client_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    await client_service.delete_client(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, client_id=client_id)
    return MessageResponse(message="Client deleted.")


@router.post("/{client_id}/archive", response_model=ClientOut)
async def archive_client(
    client_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    client = await client_service.archive_client(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, client_id=client_id)
    return ClientOut.model_validate(client)
