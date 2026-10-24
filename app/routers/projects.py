import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext
from app.core.pagination import total_pages
from app.database import get_db
from app.dependencies import get_auth_context, require_role
from app.models.membership import MembershipRole
from app.models.project import ProjectStatus
from app.schemas.common import MessageResponse, Page
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate, ProjectWithStats
from app.services import project_service

router = APIRouter()


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreate,
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.create_project(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, data=payload.model_dump()
    )
    return ProjectOut.model_validate(project)


@router.get("", response_model=Page[ProjectOut])
async def list_projects(
    search: str | None = None,
    status: ProjectStatus | None = None,
    client_id: uuid.UUID | None = None,
    include_archived: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    items, total = await project_service.list_projects(
        db, tenant_id=ctx.tenant_id, search=search, status=status, client_id=client_id,
        include_archived=include_archived, page=page, page_size=page_size,
    )
    return Page(
        items=[ProjectOut.model_validate(p) for p in items],
        total=total, page=page, page_size=page_size, total_pages=total_pages(total, page_size),
    )


@router.get("/{project_id}", response_model=ProjectWithStats)
async def get_project(
    project_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)
):
    project = await project_service.get_project(db, tenant_id=ctx.tenant_id, project_id=project_id)
    stats = await project_service.get_project_stats(db, tenant_id=ctx.tenant_id, project_id=project_id)
    return ProjectWithStats(**ProjectOut.model_validate(project).model_dump(), **stats)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.update_project(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, project_id=project_id,
        data=payload.model_dump(exclude_unset=True),
    )
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", response_model=MessageResponse)
async def delete_project(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    await project_service.delete_project(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, project_id=project_id)
    return MessageResponse(message="Project deleted.")
