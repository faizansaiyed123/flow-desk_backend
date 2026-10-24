"""Tenant, team-membership, and invitation business logic."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.invitation import Invitation, InvitationStatus
from app.models.membership import ROLE_RANK, Membership, MembershipRole
from app.models.tenant import Tenant
from app.models.user import User
from app.security import generate_secret_token, hash_password
from app.services import activity_service
from app.services.email_service import send_invitation_email

INVITATION_TTL = timedelta(days=7)


async def update_tenant(
    db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, name: str | None, logo_url: str | None
) -> Tenant:
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise NotFoundError("Workspace not found.")
    if name is not None:
        tenant.name = name
    if logo_url is not None:
        tenant.logo_url = logo_url
    await db.flush()
    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action="workspace.updated",
        entity_type="tenant", entity_id=tenant.id, entity_label=tenant.name,
    )
    return tenant


async def list_team_members(db: AsyncSession, *, tenant_id: uuid.UUID) -> list[Membership]:
    result = await db.execute(
        select(Membership)
        .options(joinedload(Membership.user))
        .where(Membership.tenant_id == tenant_id)
        .order_by(Membership.created_at.asc())
    )
    return list(result.scalars().all())


async def update_member_role(
    db: AsyncSession, *, tenant_id: uuid.UUID, membership_id: uuid.UUID, new_role: MembershipRole,
    actor_role: MembershipRole, actor_membership_id: uuid.UUID,
) -> Membership:
    membership = await db.get(Membership, membership_id)
    if not membership or membership.tenant_id != tenant_id:
        raise NotFoundError("Team member not found.")

    if membership.role == MembershipRole.OWNER and new_role != MembershipRole.OWNER:
        # Prevent demoting the last owner — a tenant must always have one.
        owners = await db.execute(
            select(Membership).where(Membership.tenant_id == tenant_id, Membership.role == MembershipRole.OWNER)
        )
        if len(owners.scalars().all()) <= 1:
            raise ValidationError("A workspace must have at least one owner.")

    if new_role == MembershipRole.OWNER and ROLE_RANK[actor_role] < ROLE_RANK[MembershipRole.OWNER]:
        raise ValidationError("Only an owner can promote another member to owner.")

    membership.role = new_role
    await db.flush()
    return membership


async def remove_member(
    db: AsyncSession, *, tenant_id: uuid.UUID, membership_id: uuid.UUID, actor_membership_id: uuid.UUID
) -> None:
    membership = await db.get(Membership, membership_id)
    if not membership or membership.tenant_id != tenant_id:
        raise NotFoundError("Team member not found.")
    if membership.id == actor_membership_id:
        raise ValidationError("You cannot remove yourself from the workspace.")
    if membership.role == MembershipRole.OWNER:
        owners = await db.execute(
            select(Membership).where(Membership.tenant_id == tenant_id, Membership.role == MembershipRole.OWNER)
        )
        if len(owners.scalars().all()) <= 1:
            raise ValidationError("A workspace must have at least one owner.")
    await db.delete(membership)
    await db.flush()


async def create_invitation(
    db: AsyncSession, *, tenant_id: uuid.UUID, inviter: User, email: str, role: MembershipRole
) -> Invitation:
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise NotFoundError("Workspace not found.")

    existing_user = await db.execute(select(User).where(User.email == email.lower()))
    user = existing_user.scalar_one_or_none()
    if user:
        already_member = await db.execute(
            select(Membership).where(Membership.tenant_id == tenant_id, Membership.user_id == user.id)
        )
        if already_member.scalar_one_or_none():
            raise ConflictError("This person is already a member of the workspace.")

    pending = await db.execute(
        select(Invitation).where(
            Invitation.tenant_id == tenant_id,
            Invitation.email == email.lower(),
            Invitation.status == InvitationStatus.PENDING,
        )
    )
    if pending.scalar_one_or_none():
        raise ConflictError("An invitation is already pending for this email.")

    invitation = Invitation(
        tenant_id=tenant_id,
        email=email.lower(),
        role=role,
        token=generate_secret_token(),
        invited_by_id=inviter.id,
        expires_at=datetime.now(timezone.utc) + INVITATION_TTL,
    )
    db.add(invitation)
    await db.flush()

    from app.config import get_settings
    settings = get_settings()
    accept_url = f"{settings.FRONTEND_URL}/accept-invite?token={invitation.token}"
    send_invitation_email(to=email, tenant_name=tenant.name, inviter_name=inviter.full_name, accept_url=accept_url)

    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=inviter.id, action="member.invited",
        entity_type="invitation", entity_id=invitation.id, entity_label=email,
    )
    return invitation


async def list_invitations(db: AsyncSession, *, tenant_id: uuid.UUID) -> list[Invitation]:
    result = await db.execute(
        select(Invitation).where(Invitation.tenant_id == tenant_id).order_by(Invitation.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_invitation(db: AsyncSession, *, tenant_id: uuid.UUID, invitation_id: uuid.UUID) -> None:
    invitation = await db.get(Invitation, invitation_id)
    if not invitation or invitation.tenant_id != tenant_id:
        raise NotFoundError("Invitation not found.")
    invitation.status = InvitationStatus.REVOKED
    await db.flush()


async def preview_invitation(db: AsyncSession, *, token: str) -> tuple[Invitation, Tenant, bool]:
    result = await db.execute(select(Invitation).where(Invitation.token == token))
    invitation = result.scalar_one_or_none()
    if not invitation or invitation.status != InvitationStatus.PENDING:
        raise NotFoundError("This invitation is invalid or has already been used.")
    if invitation.expires_at < datetime.now(timezone.utc):
        invitation.status = InvitationStatus.EXPIRED
        await db.flush()
        raise ValidationError("This invitation has expired.")

    tenant = await db.get(Tenant, invitation.tenant_id)
    existing = await db.execute(select(User).where(User.email == invitation.email))
    is_new_user = existing.scalar_one_or_none() is None
    return invitation, tenant, is_new_user


async def accept_invitation(
    db: AsyncSession, *, token: str, full_name: str | None, password: str | None
) -> tuple[User, Tenant, Membership]:
    invitation, tenant, is_new_user = await preview_invitation(db, token=token)

    result = await db.execute(select(User).where(User.email == invitation.email))
    user = result.scalar_one_or_none()

    if user is None:
        if not full_name or not password:
            raise ValidationError("Full name and password are required to create your account.")
        user = User(
            email=invitation.email,
            hashed_password=hash_password(password),
            full_name=full_name,
            is_email_verified=True,  # accepting a workspace invite implicitly verifies the email
        )
        db.add(user)
        await db.flush()

    already_member = await db.execute(
        select(Membership).where(Membership.tenant_id == tenant.id, Membership.user_id == user.id)
    )
    if already_member.scalar_one_or_none():
        raise ConflictError("You are already a member of this workspace.")

    membership = Membership(user_id=user.id, tenant_id=tenant.id, role=invitation.role)
    db.add(membership)
    invitation.status = InvitationStatus.ACCEPTED
    await db.flush()

    await activity_service.log_activity(
        db, tenant_id=tenant.id, actor_id=user.id, action="member.joined",
        entity_type="membership", entity_id=membership.id, entity_label=user.full_name,
    )
    return user, tenant, membership
