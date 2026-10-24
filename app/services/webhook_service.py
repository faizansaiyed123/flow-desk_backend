"""Webhook management and delivery.

`trigger_event` is called by other services (invoices, tasks, projects)
whenever something webhook-worthy happens. It looks up active webhooks
subscribed to that event for the tenant, POSTs a signed payload to each,
and always logs the outcome to WebhookDelivery — so a user can actually
debug a broken integration instead of wondering why it silently stopped
working (this delivery log is itself a small differentiator most portfolio
CRUD projects skip).

Delivery is fire-and-forget from the caller's perspective (best-effort,
short timeout) so a slow or dead external endpoint never blocks or fails
the primary request that triggered the event.
"""
import json
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.webhook import Webhook, WebhookDelivery
from app.security import generate_webhook_secret, sign_webhook_payload

DELIVERY_TIMEOUT_SECONDS = 5.0


async def create_webhook(
    db: AsyncSession, *, tenant_id: uuid.UUID, target_url: str, events: list[str], description: str | None
) -> Webhook:
    webhook = Webhook(
        tenant_id=tenant_id, target_url=target_url, events=events,
        secret=generate_webhook_secret(), description=description,
    )
    db.add(webhook)
    await db.flush()
    return webhook


async def list_webhooks(db: AsyncSession, *, tenant_id: uuid.UUID) -> list[Webhook]:
    result = await db.execute(select(Webhook).where(Webhook.tenant_id == tenant_id).order_by(Webhook.created_at.desc()))
    return list(result.scalars().all())


async def get_webhook(db: AsyncSession, *, tenant_id: uuid.UUID, webhook_id: uuid.UUID) -> Webhook:
    result = await db.execute(select(Webhook).where(Webhook.id == webhook_id, Webhook.tenant_id == tenant_id))
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise NotFoundError("Webhook not found.")
    return webhook


async def update_webhook(
    db: AsyncSession, *, tenant_id: uuid.UUID, webhook_id: uuid.UUID, data: dict
) -> Webhook:
    webhook = await get_webhook(db, tenant_id=tenant_id, webhook_id=webhook_id)
    for key, value in data.items():
        setattr(webhook, key, value)
    await db.flush()
    return webhook


async def delete_webhook(db: AsyncSession, *, tenant_id: uuid.UUID, webhook_id: uuid.UUID) -> None:
    webhook = await get_webhook(db, tenant_id=tenant_id, webhook_id=webhook_id)
    await db.delete(webhook)
    await db.flush()


async def list_deliveries(db: AsyncSession, *, tenant_id: uuid.UUID, webhook_id: uuid.UUID) -> list[WebhookDelivery]:
    await get_webhook(db, tenant_id=tenant_id, webhook_id=webhook_id)
    result = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.tenant_id == tenant_id, WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.attempted_at.desc())
        .limit(50)
    )
    return list(result.scalars().all())


async def trigger_event(db: AsyncSession, *, tenant_id: uuid.UUID, event: str, payload: dict) -> None:
    result = await db.execute(
        select(Webhook).where(Webhook.tenant_id == tenant_id, Webhook.is_active.is_(True))
    )
    webhooks = [w for w in result.scalars().all() if event in w.events]
    if not webhooks:
        return

    body = {"event": event, "data": payload}
    body_bytes = json.dumps(body, default=str).encode()

    async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS) as http_client:
        for webhook in webhooks:
            signature = sign_webhook_payload(webhook.secret, body_bytes)
            success = False
            status_code = None
            response_body = None
            try:
                response = await http_client.post(
                    webhook.target_url,
                    content=body_bytes,
                    headers={"Content-Type": "application/json", "X-FlowDesk-Signature": signature},
                )
                status_code = response.status_code
                response_body = response.text[:2000]
                success = 200 <= response.status_code < 300
            except httpx.HTTPError as exc:
                response_body = str(exc)[:2000]

            db.add(
                WebhookDelivery(
                    tenant_id=tenant_id, webhook_id=webhook.id, event=event, payload=body,
                    response_status=status_code, response_body=response_body, success=success,
                    attempted_at=datetime.now(timezone.utc),
                )
            )
        await db.flush()
