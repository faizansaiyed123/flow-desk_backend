import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext
from app.core.pagination import total_pages
from app.database import get_db
from app.dependencies import get_auth_context, require_role
from app.models.invoice import InvoiceStatus
from app.models.membership import MembershipRole
from app.schemas.common import MessageResponse, Page
from app.schemas.invoice import (
    InvoiceCreateManual,
    InvoiceGenerateFromTime,
    InvoiceOut,
    InvoiceSummary,
    InvoiceUpdate,
)
from app.services import invoice_service

router = APIRouter()


@router.post("", response_model=InvoiceOut, status_code=201)
async def create_manual_invoice(
    payload: InvoiceCreateManual,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    invoice = await invoice_service.create_manual_invoice(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id,
        data={**payload.model_dump(exclude={"line_items"}), "line_items": [li.model_dump() for li in payload.line_items]},
    )
    return InvoiceOut.model_validate(invoice)


@router.post("/generate-from-time", response_model=InvoiceOut, status_code=201)
async def generate_from_time(
    payload: InvoiceGenerateFromTime,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    invoice = await invoice_service.generate_invoice_from_time_entries(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, data=payload.model_dump()
    )
    return InvoiceOut.model_validate(invoice)


@router.get("", response_model=Page[InvoiceSummary])
async def list_invoices(
    status: InvoiceStatus | None = None,
    client_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    items, total = await invoice_service.list_invoices(
        db, tenant_id=ctx.tenant_id, status=status, client_id=client_id, page=page, page_size=page_size
    )
    return Page(
        items=[InvoiceSummary.model_validate(i) for i in items],
        total=total, page=page, page_size=page_size, total_pages=total_pages(total, page_size),
    )


@router.get("/{invoice_id}", response_model=InvoiceOut)
async def get_invoice(
    invoice_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    invoice = await invoice_service.get_invoice(db, tenant_id=ctx.tenant_id, invoice_id=invoice_id)
    return InvoiceOut.model_validate(invoice)


@router.patch("/{invoice_id}", response_model=InvoiceOut)
async def update_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceUpdate,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    if "line_items" in data and data["line_items"] is not None:
        data["line_items"] = [li for li in data["line_items"]]
    invoice = await invoice_service.update_invoice(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, invoice_id=invoice_id, data=data
    )
    return InvoiceOut.model_validate(invoice)


@router.post("/{invoice_id}/send", response_model=InvoiceOut)
async def send_invoice(
    invoice_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    invoice = await invoice_service.transition_status(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, invoice_id=invoice_id, new_status=InvoiceStatus.SENT
    )
    return InvoiceOut.model_validate(invoice)


@router.post("/{invoice_id}/mark-paid", response_model=InvoiceOut)
async def mark_invoice_paid(
    invoice_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    invoice = await invoice_service.transition_status(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, invoice_id=invoice_id, new_status=InvoiceStatus.PAID
    )
    return InvoiceOut.model_validate(invoice)


@router.post("/{invoice_id}/void", response_model=InvoiceOut)
async def void_invoice(
    invoice_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    invoice = await invoice_service.transition_status(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, invoice_id=invoice_id, new_status=InvoiceStatus.VOID
    )
    return InvoiceOut.model_validate(invoice)


@router.post("/{invoice_id}/mark-overdue", response_model=InvoiceOut)
async def mark_invoice_overdue(
    invoice_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    invoice = await invoice_service.transition_status(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, invoice_id=invoice_id, new_status=InvoiceStatus.OVERDUE
    )
    return InvoiceOut.model_validate(invoice)


@router.delete("/{invoice_id}", response_model=MessageResponse)
async def delete_invoice(
    invoice_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    await invoice_service.delete_invoice(db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, invoice_id=invoice_id)
    return MessageResponse(message="Invoice deleted.")
