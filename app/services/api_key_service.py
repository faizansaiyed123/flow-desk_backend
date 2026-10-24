import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.api_key import ApiKey
from app.security import generate_api_key, hash_api_key


async def create_api_key(db: AsyncSession, *, tenant_id: uuid.UUID, created_by_id: uuid.UUID, name: str) -> tuple[ApiKey, str]:
    plaintext_key, key_prefix, hashed_key = generate_api_key()
    api_key = ApiKey(
        tenant_id=tenant_id, name=name, key_prefix=key_prefix, hashed_key=hashed_key, created_by_id=created_by_id,
    )
    db.add(api_key)
    await db.flush()
    return api_key, plaintext_key


async def list_api_keys(db: AsyncSession, *, tenant_id: uuid.UUID) -> list[ApiKey]:
    result = await db.execute(select(ApiKey).where(ApiKey.tenant_id == tenant_id).order_by(ApiKey.created_at.desc()))
    return list(result.scalars().all())


async def revoke_api_key(db: AsyncSession, *, tenant_id: uuid.UUID, api_key_id: uuid.UUID) -> None:
    result = await db.execute(select(ApiKey).where(ApiKey.id == api_key_id, ApiKey.tenant_id == tenant_id))
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise NotFoundError("API key not found.")
    api_key.is_active = False
    api_key.revoked_at = datetime.now(timezone.utc)
    await db.flush()


async def resolve_api_key(db: AsyncSession, *, plaintext_key: str) -> ApiKey | None:
    """Look up an active API key by its plaintext value (used by the auth
    dependency for programmatic access — see app/dependencies.py)."""
    hashed = hash_api_key(plaintext_key)
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.hashed_key == hashed,
            ApiKey.is_active.is_(True),
            ApiKey.revoked_at.is_(None),
            (ApiKey.expires_at.is_(None) | (ApiKey.expires_at > datetime.now(timezone.utc))),
        )
    )
    api_key = result.scalar_one_or_none()
    if api_key:
        api_key.last_used_at = datetime.now(timezone.utc)
        await db.flush()
    return api_key
