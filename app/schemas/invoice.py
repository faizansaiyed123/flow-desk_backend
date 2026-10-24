import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.invoice import InvoiceStatus


class InvoiceLineItemIn(BaseModel):
    description: str = Field(min_length=1, max_length=300)
    quantity: float = Field(default=1, gt=0)
    unit_price: float = Field(ge=0)


class InvoiceLineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    quantity: float
    unit_price: float
    amount: float
    position: int


class InvoiceCreateManual(BaseModel):
    client_id: uuid.UUID
    project_id: uuid.UUID | None = None
    issue_date: date
    due_date: date
    tax_rate: float = Field(default=0, ge=0, le=100)
    notes: str | None = None
    line_items: list[InvoiceLineItemIn] = Field(min_length=1)


class InvoiceGenerateFromTime(BaseModel):
    """Generate an invoice from all not-yet-invoiced billable time entries
    on a project — the core "stop tracking time, start billing for it"
    workflow the whole time-tracking module exists to feed."""

    project_id: uuid.UUID
    issue_date: date
    due_date: date
    tax_rate: float = Field(default=0, ge=0, le=100)
    notes: str | None = None


class InvoiceUpdate(BaseModel):
    issue_date: date | None = None
    due_date: date | None = None
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    notes: str | None = None
    line_items: list[InvoiceLineItemIn] | None = None


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    client_id: uuid.UUID
    project_id: uuid.UUID | None
    status: InvoiceStatus
    issue_date: date
    due_date: date
    subtotal: float
    tax_rate: float
    tax_amount: float
    total: float
    notes: str | None
    paid_at: date | None
    line_items: list[InvoiceLineItemOut]
    created_at: datetime


class InvoiceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    client_id: uuid.UUID
    status: InvoiceStatus
    issue_date: date
    due_date: date
    total: float
