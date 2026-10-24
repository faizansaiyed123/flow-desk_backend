"""FastAPI dependency-injection functions for auth, tenancy, and RBAC.

These are the single choke point every protected route goes through, which
is what makes tenant isolation structural rather than "remember to filter":
`get_auth_context` resolves the JWT, re-validates that the membership it
claims still exists and is active, and hands back an `AuthContext` that
every service function requires in order to touch tenant data.
"""
import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.database import get_db
from app.models.membership import ROLE_RANK, Membership, MembershipRole
from app.models.user import User
from app.security import decode_token


async def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization.split(" ", 1)[1]


async def get_current_user(
    token: str = Depends(get_bearer_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive.")
    return user


async def get_auth_context(
    token: str = Depends(get_bearer_token),
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> AuthContext:
    """Resolve the full tenant-scoped auth context for a request.

    Two credential types are accepted on the same Bearer header:
    - A JWT access token (issued by /auth/login etc.), carrying `tenant_id`
      in its claims.
    - A FlowDesk API key (`fd_live_...`, issued via /api-keys), used for
      programmatic/integration access. An API key's effective role is
      resolved live from the membership of the user who created it, so
      revoking or demoting that person immediately narrows what the key
      can do — the key is never a standing grant independent of a real
      membership.
    """
    if token.startswith("fd_live_"):
        from app.services.api_key_service import resolve_api_key

        api_key = await resolve_api_key(db, plaintext_key=token)
        if not api_key:
            raise HTTPException(status_code=401, detail="Invalid or revoked API key.")
        if x_tenant_id and uuid.UUID(x_tenant_id) != api_key.tenant_id:
            raise HTTPException(status_code=403, detail="API key is not valid for the requested tenant.")

        m_result = await db.execute(
            select(Membership).where(
                Membership.user_id == api_key.created_by_id, Membership.tenant_id == api_key.tenant_id
            )
        )
        membership = m_result.scalar_one_or_none()
        if not membership:
            raise HTTPException(status_code=403, detail="The user who created this API key is no longer a member of this workspace.")
        user = await db.get(User, api_key.created_by_id)
        return AuthContext(user=user, tenant_id=api_key.tenant_id, role=membership.role, membership_id=membership.id)

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    tenant_id_claim = payload.get("tenant_id")
    if not tenant_id_claim:
        raise HTTPException(status_code=401, detail="Token has no active tenant. Select a tenant first.")
    if x_tenant_id and x_tenant_id != tenant_id_claim:
        raise HTTPException(status_code=403, detail="Token is not valid for the requested tenant.")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive.")

    tenant_id = uuid.UUID(tenant_id_claim)
    m_result = await db.execute(
        select(Membership).where(Membership.user_id == user.id, Membership.tenant_id == tenant_id)
    )
    membership = m_result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this tenant.")

    return AuthContext(user=user, tenant_id=tenant_id, role=membership.role, membership_id=membership.id)


def require_role(minimum_role: MembershipRole):
    """Dependency factory: 403s unless the caller's role meets the minimum.

    Role hierarchy: viewer < member < admin < owner. Usage:
        @router.delete(...)
        async def delete_project(ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN))): ...
    """

    async def _dependency(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if ROLE_RANK[ctx.role] < ROLE_RANK[minimum_role]:
            raise HTTPException(
                status_code=403,
                detail=f"This action requires the '{minimum_role.value}' role or higher.",
            )
        return ctx

    return _dependency
