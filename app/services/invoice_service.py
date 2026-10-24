import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.pagination import paginate
from app.models.client import Client
from app.models.invoice import Invoice, InvoiceLineItem, InvoiceStatus
from app.models.time_entry import TimeEntry
from app.services import activity_service, webhook_service
from app.services.project_service import get_project

VALID_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.DRAFT: {InvoiceStatus.SENT, InvoiceStatus.VOID},
    InvoiceStatus.SENT: {InvoiceStatus.PAID, InvoiceStatus.OVERDUE, InvoiceStatus.VOID},
    InvoiceStatus.OVERDUE: {InvoiceStatus.PAID, InvoiceStatus.VOID},
    InvoiceStatus.PAID: set(),
    InvoiceStatus.VOID: set(),
}


async def _next_invoice_number(db: AsyncSession, *, tenant_id: uuid.UUID) -> str:
    count = (
        await db.execute(select(func.count()).select_from(Invoice).where(Invoice.tenant_id == tenant_id))
    ).scalar_one()
    return f"INV-{count + 1:04d}"


async def _validate_client(db: AsyncSession, *, tenant_id: uuid.UUID, client_id: uuid.UUID) -> Client:
    result = await db.execute(select(Client).where(Client.id == client_id, Client.tenant_id == tenant_id))
    client = result.scalar_one_or_none()
    if not client:
        raise ValidationError("The selected client does not exist in this workspace.")
    return client


def _recompute_totals(invoice: Invoice) -> None:
    subtotal = sum(float(li.amount) for li in invoice.line_items)
    tax_amount = subtotal * (float(invoice.tax_rate) / 100.0)
    invoice.subtotal = round(subtotal, 2)
    invoice.tax_amount = round(tax_amount, 2)
    invoice.total = round(subtotal + tax_amount, 2)


async def create_manual_invoice(
    db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, data: dict
) -> Invoice:
    await _validate_client(db, tenant_id=tenant_id, client_id=data["client_id"])
    if data.get("project_id"):
        await get_project(db, tenant_id=tenant_id, project_id=data["project_id"])

    invoice = Invoice(
        tenant_id=tenant_id,
        invoice_number=await _next_invoice_number(db, tenant_id=tenant_id),
        client_id=data["client_id"], project_id=data.get("project_id"),
        issue_date=data["issue_date"], due_date=data["due_date"],
        tax_rate=data.get("tax_rate", 0), notes=data.get("notes"),
    )
    db.add(invoice)
    await db.flush()

    for position, item in enumerate(data["line_items"]):
        amount = round(item["quantity"] * item["unit_price"], 2)
        db.add(InvoiceLineItem(
            tenant_id=tenant_id, invoice_id=invoice.id, description=item["description"],
            quantity=item["quantity"], unit_price=item["unit_price"], amount=amount, position=position,
        ))
    await db.flush()
    await db.refresh(invoice, attribute_names=["line_items"])
    _recompute_totals(invoice)
    await db.flush()

    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action="invoice.created",
        entity_type="invoice", entity_id=invoice.id, entity_label=invoice.invoice_number,
    )
    return invoice


async def generate_invoice_from_time_entries(
    db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, data: dict
) -> Invoice:
    project = await get_project(db, tenant_id=tenant_id, project_id=data["project_id"])
    if not project.client_id:
        raise ValidationError("This project has no client assigned — assign one before invoicing.")
    if not project.hourly_rate:
        raise ValidationError("This project has no hourly rate set — set one before generating a time-based invoice.")

    result = await db.execute(
        select(TimeEntry).where(
            TimeEntry.tenant_id == tenant_id, TimeEntry.project_id == project.id,
            TimeEntry.is_billable.is_(True), TimeEntry.is_invoiced.is_(False),
            TimeEntry.ended_at.is_not(None),
        )
    )
    entries = list(result.scalars().all())
    if not entries:
        raise ValidationError("There are no unbilled, completed time entries for this project.")

    invoice = Invoice(
        tenant_id=tenant_id,
        invoice_number=await _next_invoice_number(db, tenant_id=tenant_id),
        client_id=project.client_id, project_id=project.id,
        issue_date=data["issue_date"], due_date=data["due_date"],
        tax_rate=data.get("tax_rate", 0), notes=data.get("notes"),
    )
    db.add(invoice)
    await db.flush()

    total_minutes = sum(e.duration_minutes or 0 for e in entries)
    hours = round(total_minutes / 60.0, 2)
    rate = float(project.hourly_rate)
    amount = round(hours * rate, 2)
    db.add(InvoiceLineItem(
        tenant_id=tenant_id, invoice_id=invoice.id,
        description=f"{project.name} — {hours} hours @ ${rate:.2f}/hr",
        quantity=hours, unit_price=rate, amount=amount, position=0,
    ))
    for entry in entries:
        entry.is_invoiced = True
        entry.invoice_id = invoice.id
    await db.flush()
    await db.refresh(invoice, attribute_names=["line_items"])
    _recompute_totals(invoice)
    await db.flush()

    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action="invoice.created",
        entity_type="invoice", entity_id=invoice.id, entity_label=invoice.invoice_number,
        metadata={"generated_from_time_entries": True, "entry_count": len(entries)},
    )
    return invoice


async def get_invoice(db: AsyncSession, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID) -> Invoice:
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise NotFoundError("Invoice not found.")
    await db.refresh(invoice, attribute_names=["line_items"])
    return invoice


async def list_invoices(
    db: AsyncSession, *, tenant_id: uuid.UUID, status: InvoiceStatus | None = None,
    client_id: uuid.UUID | None = None, page: int = 1, page_size: int = 20,
) -> tuple[list[Invoice], int]:
    stmt = select(Invoice).where(Invoice.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(Invoice.status == status)
    if client_id:
        stmt = stmt.where(Invoice.client_id == client_id)
    stmt = stmt.order_by(Invoice.issue_date.desc())
    return await paginate(db, stmt, page=page, page_size=page_size)


async def update_invoice(
    db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, invoice_id: uuid.UUID, data: dict
) -> Invoice:
    invoice = await get_invoice(db, tenant_id=tenant_id, invoice_id=invoice_id)
    if invoice.status != InvoiceStatus.DRAFT:
        raise ValidationError("Only draft invoices can be edited.")

    line_items = data.pop("line_items", None)
    for key, value in data.items():
        if value is not None:
            setattr(invoice, key, value)

    if line_items is not None:
        for existing in list(invoice.line_items):
            await db.delete(existing)
        await db.flush()
        for position, item in enumerate(line_items):
            amount = round(item["quantity"] * item["unit_price"], 2)
            db.add(InvoiceLineItem(
                tenant_id=tenant_id, invoice_id=invoice.id, description=item["description"],
                quantity=item["quantity"], unit_price=item["unit_price"], amount=amount, position=position,
            ))
        await db.flush()
        await db.refresh(invoice, attribute_names=["line_items"])

    _recompute_totals(invoice)
    await db.flush()
    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action="invoice.updated",
        entity_type="invoice", entity_id=invoice.id, entity_label=invoice.invoice_number,
    )
    return invoice


async def transition_status(
    db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, invoice_id: uuid.UUID, new_status: InvoiceStatus
) -> Invoice:
    invoice = await get_invoice(db, tenant_id=tenant_id, invoice_id=invoice_id)
    allowed = VALID_TRANSITIONS.get(invoice.status, set())
    if new_status not in allowed:
        raise ValidationError(f"Cannot transition an invoice from '{invoice.status.value}' to '{new_status.value}'.")

    invoice.status = new_status
    if new_status == InvoiceStatus.PAID:
        invoice.paid_at = date.today()
    await db.flush()

    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action=f"invoice.{new_status.value}",
        entity_type="invoice", entity_id=invoice.id, entity_label=invoice.invoice_number,
    )

    if new_status == InvoiceStatus.SENT:
        await webhook_service.trigger_event(
            db, tenant_id=tenant_id, event="invoice.sent",
            payload={"invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number, "total": float(invoice.total)},
        )
    elif new_status == InvoiceStatus.PAID:
        await webhook_service.trigger_event(
            db, tenant_id=tenant_id, event="invoice.paid",
            payload={"invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number, "total": float(invoice.total)},
        )
    return invoice


async def delete_invoice(db: AsyncSession, *, tenant_id: uuid.UUID, actor_id: uuid.UUID, invoice_id: uuid.UUID) -> None:
    invoice = await get_invoice(db, tenant_id=tenant_id, invoice_id=invoice_id)
    if invoice.status != InvoiceStatus.DRAFT:
        raise ValidationError("Only draft invoices can be deleted.")

    # Release any time entries this invoice had claimed (shouldn't normally
    # happen for a still-draft invoice generated from time entries, but
    # kept for safety/consistency).
    result = await db.execute(select(TimeEntry).where(TimeEntry.invoice_id == invoice.id))
    for entry in result.scalars().all():
        entry.is_invoiced = False
        entry.invoice_id = None

    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=actor_id, action="invoice.deleted",
        entity_type="invoice", entity_id=invoice.id, entity_label=invoice.invoice_number,
    )
    await db.delete(invoice)
    await db.flush()
