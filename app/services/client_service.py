"""Client (customer) service. Every function is tenant-scoped: it takes
tenant_id explicitly and every query filters on it, so it's structurally
impossible to fetch another tenant's data through this module."""
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import paginate
from app.models.client import Client
from app.models.invoice import Invoice, InvoiceStatus
from app.models.project import Project, ProjectStatus
from app.services import activity_service


async def create_client(db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, data: dict) -> Client:
    client = Client(tenant_id=tenant_id, **data)
    db.add(client)
    await db.flush()
    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action="client.created",
        entity_type="client", entity_id=client.id, entity_label=client.name,
    )
    return client


async def get_client(db: AsyncSession, *, tenant_id: uuid.UUID, client_id: uuid.UUID) -> Client:
    result = await db.execute(select(Client).where(Client.id == client_id, Client.tenant_id == tenant_id))
    client = result.scalar_one_or_none()
    if not client:
        raise NotFoundError("Client not found.")
    return client


async def list_clients(
    db: AsyncSession, *, tenant_id: uuid.UUID, search: str | None = None,
    include_archived: bool = False, page: int = 1, page_size: int = 20,
) -> tuple[list[Client], int]:
    stmt = select(Client).where(Client.tenant_id == tenant_id)
    if not include_archived:
        stmt = stmt.where(Client.is_archived.is_(False))
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(func.lower(Client.name).like(pattern), func.lower(Client.company).like(pattern))
        )
    stmt = stmt.order_by(Client.name.asc())
    return await paginate(db, stmt, page=page, page_size=page_size)


async def update_client(
    db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, client_id: uuid.UUID, data: dict
) -> Client:
    client = await get_client(db, tenant_id=tenant_id, client_id=client_id)
    for key, value in data.items():
        if value is not None:
            setattr(client, key, value)
    await db.flush()
    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action="client.updated",
        entity_type="client", entity_id=client.id, entity_label=client.name,
    )
    return client


async def delete_client(db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, client_id: uuid.UUID) -> None:
    client = await get_client(db, tenant_id=tenant_id, client_id=client_id)
    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action="client.deleted",
        entity_type="client", entity_id=client.id, entity_label=client.name,
    )
    await db.delete(client)
    await db.flush()


async def archive_client(db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, client_id: uuid.UUID) -> Client:
    client = await get_client(db, tenant_id=tenant_id, client_id=client_id)
    client.is_archived = not client.is_archived
    await db.flush()
    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action="client.archived",
        entity_type="client", entity_id=client.id, entity_label=client.name,
    )
    return client


async def get_client_stats(db: AsyncSession, *, tenant_id: uuid.UUID, client_id: uuid.UUID) -> dict:
    project_count = (
        await db.execute(
            select(func.count()).select_from(Project).where(
                Project.tenant_id == tenant_id, Project.client_id == client_id
            )
        )
    ).scalar_one()
    active_project_count = (
        await db.execute(
            select(func.count()).select_from(Project).where(
                Project.tenant_id == tenant_id,
                Project.client_id == client_id,
                Project.status == ProjectStatus.ACTIVE,
            )
        )
    ).scalar_one()
    total_invoiced = (
        await db.execute(
            select(func.coalesce(func.sum(Invoice.total), 0)).where(
                Invoice.tenant_id == tenant_id, Invoice.client_id == client_id,
                Invoice.status != InvoiceStatus.VOID,
            )
        )
    ).scalar_one()
    total_outstanding = (
        await db.execute(
            select(func.coalesce(func.sum(Invoice.total), 0)).where(
                Invoice.tenant_id == tenant_id, Invoice.client_id == client_id,
                Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.OVERDUE]),
            )
        )
    ).scalar_one()
    return {
        "project_count": project_count,
        "active_project_count": active_project_count,
        "total_invoiced": float(total_invoiced),
        "total_outstanding": float(total_outstanding),
    }
