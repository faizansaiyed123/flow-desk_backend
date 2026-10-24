import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext
from app.database import get_db
from app.dependencies import get_auth_context, get_current_user, require_role
from app.models.membership import MembershipRole
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.tenant import (
    CreateInvitationRequest,
    InvitationOut,
    InvitationPreview,
    TenantOut,
    UpdateTenantRequest,
)
from app.schemas.auth import AcceptInvitationRequest, TokenPair
from app.schemas.user import TeamMemberOut, UpdateMemberRoleRequest, UserOut
from app.services import tenant_service

router = APIRouter()


@router.get("/current", response_model=TenantOut)
async def get_current_tenant(ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)):
    tenant = await db.get(Tenant, ctx.tenant_id)
    return TenantOut.model_validate(tenant)


@router.patch("/current", response_model=TenantOut)
async def update_current_tenant(
    payload: UpdateTenantRequest,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    tenant = await tenant_service.update_tenant(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, name=payload.name, logo_url=payload.logo_url
    )
    return TenantOut.model_validate(tenant)


@router.get("/members", response_model=list[TeamMemberOut])
async def list_members(ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)):
    memberships = await tenant_service.list_team_members(db, tenant_id=ctx.tenant_id)
    return [
        TeamMemberOut(
            membership_id=m.id, user=UserOut.model_validate(m.user), role=m.role, joined_at=m.created_at
        )
        for m in memberships
    ]


@router.patch("/members/{membership_id}/role", response_model=MessageResponse)
async def update_member_role(
    membership_id: uuid.UUID,
    payload: UpdateMemberRoleRequest,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    await tenant_service.update_member_role(
        db, tenant_id=ctx.tenant_id, membership_id=membership_id, new_role=payload.role,
        actor_role=ctx.role, actor_membership_id=ctx.membership_id,
    )
    return MessageResponse(message="Role updated.")


@router.delete("/members/{membership_id}", response_model=MessageResponse)
async def remove_member(
    membership_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    await tenant_service.remove_member(
        db, tenant_id=ctx.tenant_id, membership_id=membership_id, actor_membership_id=ctx.membership_id
    )
    return MessageResponse(message="Member removed.")


@router.post("/invitations", response_model=InvitationOut, status_code=201)
async def create_invitation(
    payload: CreateInvitationRequest,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    invitation = await tenant_service.create_invitation(
        db, tenant_id=ctx.tenant_id, inviter=ctx.user, email=payload.email, role=payload.role
    )
    return InvitationOut.model_validate(invitation)


@router.get("/invitations", response_model=list[InvitationOut])
async def list_invitations(
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)), db: AsyncSession = Depends(get_db)
):
    invitations = await tenant_service.list_invitations(db, tenant_id=ctx.tenant_id)
    return [InvitationOut.model_validate(i) for i in invitations]


@router.delete("/invitations/{invitation_id}", response_model=MessageResponse)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    await tenant_service.revoke_invitation(db, tenant_id=ctx.tenant_id, invitation_id=invitation_id)
    return MessageResponse(message="Invitation revoked.")


# --- Public (unauthenticated) invitation acceptance flow ---

public_router = APIRouter()


@public_router.get("/invitations/{token}", response_model=InvitationPreview)
async def preview_invitation(token: str, db: AsyncSession = Depends(get_db)):
    invitation, tenant, is_new_user = await tenant_service.preview_invitation(db, token=token)
    return InvitationPreview(
        tenant_name=tenant.name, email=invitation.email, role=invitation.role, is_new_user=is_new_user
    )


@public_router.post("/invitations/accept", response_model=TokenPair)
async def accept_invitation(payload: AcceptInvitationRequest, db: AsyncSession = Depends(get_db)):
    user, tenant, membership = await tenant_service.accept_invitation(
        db, token=payload.token, full_name=payload.full_name, password=payload.password
    )
    from app.security import create_token

    access = create_token(subject=str(user.id), token_type="access", tenant_id=str(tenant.id))
    refresh = create_token(subject=str(user.id), token_type="refresh", tenant_id=str(tenant.id))
    return TokenPair(access_token=access, refresh_token=refresh)
