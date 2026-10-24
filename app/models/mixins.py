"""Reusable declarative mixins shared by ORM models."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Computed client-side (Python) rather than via a server-side onupdate,
    # so the ORM already has the new value in-memory after flush — no
    # extra `db.refresh()` round-trip needed (and no async-greenlet trap
    # from lazily loading a server-computed value outside an await).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class TenantScopedMixin:
    """Marks a table as belonging to exactly one tenant.

    Every tenant-scoped table gets a NOT NULL tenant_id FK with an index,
    so the query-scoping layer (see app/core/tenant_scope.py) can never be
    bypassed by a forgotten filter — the column itself is mandatory and the
    services module always filters on it.
    """

    @classmethod
    def __declare_last__(cls):
        pass

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
