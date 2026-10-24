"""Audit/activity log helper. Every mutating service call in the app should
call `log_activity` so the tenant's activity feed and audit trail stay
complete without each router having to remember to do it separately."""
import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityLog


async def log_activity(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    entity_label: str | None = None,
    metadata: dict | None = None,
) -> ActivityLog:
    entry = ActivityLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label,
        metadata_json=metadata,
    )
    db.add(entry)
    await db.flush()
    return entry


async def list_activity(
    db: AsyncSession, *, tenant_id: uuid.UUID, limit: int = 50, offset: int = 0,
    entity_type: str | None = None, entity_id: uuid.UUID | None = None,
) -> list[ActivityLog]:
    stmt = select(ActivityLog).where(ActivityLog.tenant_id == tenant_id)
    if entity_type:
        stmt = stmt.where(ActivityLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(ActivityLog.entity_id == entity_id)
    stmt = stmt.order_by(desc(ActivityLog.created_at)).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())
