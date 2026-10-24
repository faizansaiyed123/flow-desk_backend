import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext
from app.database import get_db
from app.dependencies import require_role
from app.models.membership import MembershipRole
from app.schemas.common import MessageResponse
from app.schemas.webhook import (
    WebhookCreate,
    WebhookCreatedOut,
    WebhookDeliveryOut,
    WebhookOut,
    WebhookUpdate,
)
from app.services import webhook_service

router = APIRouter()


@router.post("", response_model=WebhookCreatedOut, status_code=201)
async def create_webhook(
    payload: WebhookCreate,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    webhook = await webhook_service.create_webhook(
        db, tenant_id=ctx.tenant_id, target_url=payload.target_url, events=payload.events,
        description=payload.description,
    )
    return WebhookCreatedOut(**WebhookOut.model_validate(webhook).model_dump(), secret=webhook.secret)


@router.get("", response_model=list[WebhookOut])
async def list_webhooks(ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)), db: AsyncSession = Depends(get_db)):
    webhooks = await webhook_service.list_webhooks(db, tenant_id=ctx.tenant_id)
    return [WebhookOut.model_validate(w) for w in webhooks]


@router.patch("/{webhook_id}", response_model=WebhookOut)
async def update_webhook(
    webhook_id: uuid.UUID,
    payload: WebhookUpdate,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    webhook = await webhook_service.update_webhook(
        db, tenant_id=ctx.tenant_id, webhook_id=webhook_id, data=payload.model_dump(exclude_unset=True)
    )
    return WebhookOut.model_validate(webhook)


@router.delete("/{webhook_id}", response_model=MessageResponse)
async def delete_webhook(
    webhook_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    await webhook_service.delete_webhook(db, tenant_id=ctx.tenant_id, webhook_id=webhook_id)
    return MessageResponse(message="Webhook deleted.")


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryOut])
async def list_deliveries(
    webhook_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    deliveries = await webhook_service.list_deliveries(db, tenant_id=ctx.tenant_id, webhook_id=webhook_id)
    return [WebhookDeliveryOut.model_validate(d) for d in deliveries]
