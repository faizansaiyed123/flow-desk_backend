"""Auth business logic. Function-based; each function takes an AsyncSession
plus plain arguments and returns plain data or raises a FlowDeskError
subclass — no FastAPI/HTTP concepts leak in here, so these are directly
unit-testable.
"""
import uuid
from datetime import datetime, timedelta, timezone

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, ValidationError
from app.models.membership import Membership, MembershipRole
from app.models.password_reset import PasswordResetToken
from app.models.tenant import Tenant
from app.models.user import User
from app.security import (
    create_token,
    decode_token,
    generate_secret_token,
    hash_password,
    verify_password,
)
from app.services import activity_service
from app.services.email_service import send_password_reset_email

RESET_TOKEN_TTL = timedelta(hours=1)


async def _unique_slug(db: AsyncSession, base_name: str) -> str:
    base = slugify(base_name)[:60] or "workspace"
    slug = base
    suffix = 1
    while True:
        result = await db.execute(select(Tenant).where(Tenant.slug == slug))
        if result.scalar_one_or_none() is None:
            return slug
        suffix += 1
        slug = f"{base}-{suffix}"


async def register(
    db: AsyncSession, *, full_name: str, email: str, password: str, workspace_name: str
) -> tuple[User, Tenant, Membership]:
    existing = await db.execute(select(User).where(User.email == email.lower()))
    if existing.scalar_one_or_none():
        raise ConflictError("An account with this email already exists.")

    user = User(
        email=email.lower(),
        hashed_password=hash_password(password),
        full_name=full_name,
        is_email_verified=False,
    )
    db.add(user)
    await db.flush()

    tenant = Tenant(name=workspace_name, slug=await _unique_slug(db, workspace_name))
    db.add(tenant)
    await db.flush()

    membership = Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.OWNER)
    db.add(membership)
    await db.flush()

    await activity_service.log_activity(
        db,
        tenant_id=tenant.id,
        actor_id=user.id,
        action="workspace.created",
        entity_type="tenant",
        entity_id=tenant.id,
        entity_label=tenant.name,
    )

    return user, tenant, membership


async def _get_default_membership(db: AsyncSession, user_id: uuid.UUID) -> Membership | None:
    result = await db.execute(
        select(Membership).where(Membership.user_id == user_id).order_by(Membership.created_at.asc())
    )
    return result.scalars().first()


async def login(
    db: AsyncSession, *, email: str, password: str, tenant_id: uuid.UUID | None = None
) -> tuple[User, Tenant, MembershipRole, str, str]:
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        raise AuthenticationError("Incorrect email or password.")
    if not user.is_active:
        raise AuthenticationError("This account has been deactivated.")

    if tenant_id:
        m_result = await db.execute(
            select(Membership).where(Membership.user_id == user.id, Membership.tenant_id == tenant_id)
        )
        membership = m_result.scalar_one_or_none()
        if not membership:
            raise AuthenticationError("You are not a member of the requested workspace.")
    else:
        membership = await _get_default_membership(db, user.id)
        if not membership:
            raise AuthenticationError("This account has no workspace. Contact your administrator.")

    tenant = await db.get(Tenant, membership.tenant_id)
    access = create_token(subject=str(user.id), token_type="access", tenant_id=str(tenant.id))
    refresh = create_token(subject=str(user.id), token_type="refresh", tenant_id=str(tenant.id))
    return user, tenant, membership.role, access, refresh


async def refresh_tokens(db: AsyncSession, *, refresh_token: str) -> tuple[str, str]:
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise AuthenticationError("Invalid or expired refresh token.")

    user_id = uuid.UUID(payload["sub"])
    tenant_id = payload.get("tenant_id")
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise AuthenticationError("User not found or inactive.")

    # Re-validate membership still exists (handles the case where the user
    # was removed from the tenant since the refresh token was issued).
    if tenant_id:
        m_result = await db.execute(
            select(Membership).where(
                Membership.user_id == user.id, Membership.tenant_id == uuid.UUID(tenant_id)
            )
        )
        if not m_result.scalar_one_or_none():
            raise AuthenticationError("You are no longer a member of this workspace.")

    access = create_token(subject=str(user.id), token_type="access", tenant_id=tenant_id)
    new_refresh = create_token(subject=str(user.id), token_type="refresh", tenant_id=tenant_id)
    return access, new_refresh


async def switch_tenant(db: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID) -> tuple[str, str, MembershipRole]:
    result = await db.execute(
        select(Membership).where(Membership.user_id == user_id, Membership.tenant_id == tenant_id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise AuthenticationError("You are not a member of that workspace.")

    access = create_token(subject=str(user_id), token_type="access", tenant_id=str(tenant_id))
    refresh = create_token(subject=str(user_id), token_type="refresh", tenant_id=str(tenant_id))
    return access, refresh, membership.role


async def get_memberships_with_tenants(db: AsyncSession, user_id: uuid.UUID) -> list[tuple[Membership, Tenant]]:
    result = await db.execute(
        select(Membership, Tenant)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == user_id)
    )
    return list(result.all())


async def request_password_reset(db: AsyncSession, *, email: str) -> None:
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if not user:
        # Do not reveal whether the email exists — respond as if it worked.
        return

    token = generate_secret_token()
    reset = PasswordResetToken(
        user_id=user.id, token=token, expires_at=datetime.now(timezone.utc) + RESET_TOKEN_TTL
    )
    db.add(reset)
    await db.flush()

    from app.config import get_settings
    settings = get_settings()
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    send_password_reset_email(to=user.email, reset_url=reset_url)


async def reset_password(db: AsyncSession, *, token: str, new_password: str) -> None:
    result = await db.execute(select(PasswordResetToken).where(PasswordResetToken.token == token))
    reset = result.scalar_one_or_none()
    if not reset or reset.used or reset.expires_at < datetime.now(timezone.utc):
        raise ValidationError("This password reset link is invalid or has expired.")

    user = await db.get(User, reset.user_id)
    if not user:
        raise NotFoundError("User not found.")

    user.hashed_password = hash_password(new_password)
    reset.used = True
    await db.flush()


async def change_password(db: AsyncSession, *, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise ValidationError("Current password is incorrect.")
    user.hashed_password = hash_password(new_password)
    await db.flush()
