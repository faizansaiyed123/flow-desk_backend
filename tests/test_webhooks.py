import pytest
import respx
from httpx import Response

from tests.conftest import unique_email

pytestmark = pytest.mark.asyncio


async def _setup(client, workspace_name="Acme"):
    email = unique_email()
    reg = await client.post(
        "/api/v1/auth/register",
        json={"full_name": "Owner", "email": email, "password": "supersecret123", "workspace_name": workspace_name},
    )
    token = reg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_webhook_returns_secret_once(client):
    headers = await _setup(client)
    resp = await client.post(
        "/api/v1/webhooks",
        json={"target_url": "https://example.com/hook", "events": ["invoice.sent", "invoice.paid"]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert "secret" in resp.json()
    assert len(resp.json()["secret"]) > 10


async def test_create_webhook_rejects_unknown_event(client):
    headers = await _setup(client)
    resp = await client.post(
        "/api/v1/webhooks", json={"target_url": "https://example.com/hook", "events": ["not.a.real.event"]}, headers=headers
    )
    assert resp.status_code == 422


async def test_create_webhook_rejects_non_http_url(client):
    headers = await _setup(client)
    resp = await client.post(
        "/api/v1/webhooks", json={"target_url": "ftp://example.com/hook", "events": ["invoice.sent"]}, headers=headers
    )
    assert resp.status_code == 422


async def test_list_update_delete_webhook(client):
    headers = await _setup(client)
    created = await client.post(
        "/api/v1/webhooks", json={"target_url": "https://example.com/hook", "events": ["task.created"]}, headers=headers
    )
    webhook_id = created.json()["id"]

    listed = await client.get("/api/v1/webhooks", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert "secret" not in listed.json()[0]  # secret never re-exposed after creation

    updated = await client.patch(f"/api/v1/webhooks/{webhook_id}", json={"is_active": False}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False

    deleted = await client.delete(f"/api/v1/webhooks/{webhook_id}", headers=headers)
    assert deleted.status_code == 200


@respx.mock
async def test_invoice_sent_triggers_webhook_delivery(client):
    headers = await _setup(client)
    route = respx.post("https://example.com/hook").mock(return_value=Response(200, json={"ok": True}))

    created = await client.post(
        "/api/v1/webhooks", json={"target_url": "https://example.com/hook", "events": ["invoice.sent"]}, headers=headers
    )
    webhook_id = created.json()["id"]

    c = await client.post("/api/v1/clients", json={"name": "Hook Client"}, headers=headers)
    inv = await client.post(
        "/api/v1/invoices",
        json={
            "client_id": c.json()["id"], "issue_date": "2026-01-01", "due_date": "2026-01-31",
            "line_items": [{"description": "Work", "quantity": 1, "unit_price": 100}],
        },
        headers=headers,
    )
    await client.post(f"/api/v1/invoices/{inv.json()['id']}/send", headers=headers)

    assert route.called

    deliveries = await client.get(f"/api/v1/webhooks/{webhook_id}/deliveries", headers=headers)
    assert deliveries.status_code == 200
    assert len(deliveries.json()) == 1
    assert deliveries.json()[0]["success"] is True
    assert deliveries.json()[0]["event"] == "invoice.sent"


@respx.mock
async def test_webhook_delivery_failure_is_logged_not_raised(client):
    headers = await _setup(client)
    respx.post("https://example.com/broken").mock(return_value=Response(500, text="server error"))

    created = await client.post(
        "/api/v1/webhooks", json={"target_url": "https://example.com/broken", "events": ["invoice.sent"]}, headers=headers
    )
    webhook_id = created.json()["id"]

    c = await client.post("/api/v1/clients", json={"name": "Broken Hook Client"}, headers=headers)
    inv = await client.post(
        "/api/v1/invoices",
        json={
            "client_id": c.json()["id"], "issue_date": "2026-01-01", "due_date": "2026-01-31",
            "line_items": [{"description": "Work", "quantity": 1, "unit_price": 100}],
        },
        headers=headers,
    )
    # Should NOT raise / fail the request even though the webhook endpoint 500s.
    send_resp = await client.post(f"/api/v1/invoices/{inv.json()['id']}/send", headers=headers)
    assert send_resp.status_code == 200

    deliveries = await client.get(f"/api/v1/webhooks/{webhook_id}/deliveries", headers=headers)
    assert deliveries.json()[0]["success"] is False
    assert deliveries.json()[0]["response_status"] == 500


async def test_inactive_webhook_does_not_receive_events(client):
    headers = await _setup(client)
    created = await client.post(
        "/api/v1/webhooks", json={"target_url": "https://example.com/hook", "events": ["invoice.sent"]}, headers=headers
    )
    webhook_id = created.json()["id"]
    await client.patch(f"/api/v1/webhooks/{webhook_id}", json={"is_active": False}, headers=headers)

    with respx.mock:
        route = respx.post("https://example.com/hook").mock(return_value=Response(200))
        c = await client.post("/api/v1/clients", json={"name": "Quiet Client"}, headers=headers)
        inv = await client.post(
            "/api/v1/invoices",
            json={
                "client_id": c.json()["id"], "issue_date": "2026-01-01", "due_date": "2026-01-31",
                "line_items": [{"description": "Work", "quantity": 1, "unit_price": 100}],
            },
            headers=headers,
        )
        await client.post(f"/api/v1/invoices/{inv.json()['id']}/send", headers=headers)
        assert not route.called
