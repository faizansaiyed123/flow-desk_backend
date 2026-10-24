import pytest

from tests.conftest import unique_email

pytestmark = pytest.mark.asyncio


async def _setup(client, workspace_name="Acme"):
    email = unique_email()
    reg = await client.post(
        "/api/v1/auth/register",
        json={"full_name": "Owner", "email": email, "password": "supersecret123", "workspace_name": workspace_name},
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    c = await client.post("/api/v1/clients", json={"name": "Billable Client"}, headers=headers)
    client_id = c.json()["id"]
    return headers, client_id


async def test_create_manual_invoice_computes_totals(client):
    headers, client_id = await _setup(client)
    resp = await client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "issue_date": "2026-01-01",
            "due_date": "2026-01-31",
            "tax_rate": 10,
            "line_items": [
                {"description": "Design work", "quantity": 10, "unit_price": 50},
                {"description": "Consulting", "quantity": 2, "unit_price": 100},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["subtotal"] == 700.0
    assert body["tax_amount"] == 70.0
    assert body["total"] == 770.0
    assert body["invoice_number"] == "INV-0001"
    assert body["status"] == "draft"


async def test_create_manual_invoice_invalid_client_rejected(client):
    headers, _ = await _setup(client)
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(
        "/api/v1/invoices",
        json={
            "client_id": fake_id, "issue_date": "2026-01-01", "due_date": "2026-01-31",
            "line_items": [{"description": "Work", "quantity": 1, "unit_price": 100}],
        },
        headers=headers,
    )
    assert resp.status_code == 422


async def test_member_cannot_create_invoice(client, db_session):
    from app.models.membership import Membership, MembershipRole
    from app.models.user import User
    from app.security import create_token, hash_password

    headers, client_id = await _setup(client, workspace_name="InvoiceRoleCo")
    tenant_id = (await client.get("/api/v1/tenants/current", headers=headers)).json()["id"]

    member = User(email=unique_email(), hashed_password=hash_password("pw12345678"), full_name="Mem Ber")
    db_session.add(member)
    await db_session.flush()
    db_session.add(Membership(user_id=member.id, tenant_id=tenant_id, role=MembershipRole.MEMBER))
    await db_session.commit()
    member_token = create_token(subject=str(member.id), token_type="access", tenant_id=tenant_id)

    resp = await client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id, "issue_date": "2026-01-01", "due_date": "2026-01-31",
            "line_items": [{"description": "Work", "quantity": 1, "unit_price": 100}],
        },
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403


async def test_generate_invoice_from_time_entries(client):
    headers, client_id = await _setup(client)
    p = await client.post(
        "/api/v1/projects",
        json={"name": "Time Billed Project", "client_id": client_id, "hourly_rate": 100},
        headers=headers,
    )
    project_id = p.json()["id"]

    await client.post(
        "/api/v1/time-entries",
        json={
            "project_id": project_id, "started_at": "2026-01-01T09:00:00Z",
            "ended_at": "2026-01-01T11:00:00Z", "is_billable": True,
        },
        headers=headers,
    )
    await client.post(
        "/api/v1/time-entries",
        json={
            "project_id": project_id, "started_at": "2026-01-02T09:00:00Z",
            "ended_at": "2026-01-02T10:00:00Z", "is_billable": True,
        },
        headers=headers,
    )

    resp = await client.post(
        "/api/v1/invoices/generate-from-time",
        json={"project_id": project_id, "issue_date": "2026-01-15", "due_date": "2026-02-15"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["subtotal"] == 300.0  # 3 hours @ $100
    assert len(body["line_items"]) == 1

    entries = await client.get(f"/api/v1/time-entries?project_id={project_id}", headers=headers)
    assert all(e["is_invoiced"] for e in entries.json()["items"])


async def test_generate_invoice_requires_hourly_rate(client):
    headers, client_id = await _setup(client)
    p = await client.post("/api/v1/projects", json={"name": "No Rate Project", "client_id": client_id}, headers=headers)
    project_id = p.json()["id"]
    await client.post(
        "/api/v1/time-entries",
        json={"project_id": project_id, "started_at": "2026-01-01T09:00:00Z", "ended_at": "2026-01-01T11:00:00Z"},
        headers=headers,
    )
    resp = await client.post(
        "/api/v1/invoices/generate-from-time",
        json={"project_id": project_id, "issue_date": "2026-01-15", "due_date": "2026-02-15"},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_generate_invoice_with_no_unbilled_entries_rejected(client):
    headers, client_id = await _setup(client)
    p = await client.post(
        "/api/v1/projects", json={"name": "Empty Project", "client_id": client_id, "hourly_rate": 50}, headers=headers
    )
    project_id = p.json()["id"]
    resp = await client.post(
        "/api/v1/invoices/generate-from-time",
        json={"project_id": project_id, "issue_date": "2026-01-15", "due_date": "2026-02-15"},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_invoice_status_lifecycle(client):
    headers, client_id = await _setup(client)
    resp = await client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id, "issue_date": "2026-01-01", "due_date": "2026-01-31",
            "line_items": [{"description": "Work", "quantity": 1, "unit_price": 500}],
        },
        headers=headers,
    )
    invoice_id = resp.json()["id"]

    # draft -> paid directly should be rejected
    bad = await client.post(f"/api/v1/invoices/{invoice_id}/mark-paid", headers=headers)
    assert bad.status_code == 422

    sent = await client.post(f"/api/v1/invoices/{invoice_id}/send", headers=headers)
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"

    paid = await client.post(f"/api/v1/invoices/{invoice_id}/mark-paid", headers=headers)
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"
    assert paid.json()["paid_at"] is not None

    # paid is terminal
    void_after_paid = await client.post(f"/api/v1/invoices/{invoice_id}/void", headers=headers)
    assert void_after_paid.status_code == 422


async def test_only_draft_invoices_can_be_edited_or_deleted(client):
    headers, client_id = await _setup(client)
    resp = await client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id, "issue_date": "2026-01-01", "due_date": "2026-01-31",
            "line_items": [{"description": "Work", "quantity": 1, "unit_price": 500}],
        },
        headers=headers,
    )
    invoice_id = resp.json()["id"]
    await client.post(f"/api/v1/invoices/{invoice_id}/send", headers=headers)

    edit = await client.patch(f"/api/v1/invoices/{invoice_id}", json={"notes": "changed"}, headers=headers)
    assert edit.status_code == 422

    delete = await client.delete(f"/api/v1/invoices/{invoice_id}", headers=headers)
    assert delete.status_code == 422


async def test_update_draft_invoice_line_items_recomputes_totals(client):
    headers, client_id = await _setup(client)
    resp = await client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id, "issue_date": "2026-01-01", "due_date": "2026-01-31",
            "line_items": [{"description": "Work", "quantity": 1, "unit_price": 500}],
        },
        headers=headers,
    )
    invoice_id = resp.json()["id"]

    updated = await client.patch(
        f"/api/v1/invoices/{invoice_id}",
        json={"line_items": [{"description": "Revised work", "quantity": 2, "unit_price": 300}]},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["subtotal"] == 600.0
    assert len(updated.json()["line_items"]) == 1


async def test_list_invoices_filter_by_status(client):
    headers, client_id = await _setup(client)
    r1 = await client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id, "issue_date": "2026-01-01", "due_date": "2026-01-31",
            "line_items": [{"description": "Work", "quantity": 1, "unit_price": 100}],
        },
        headers=headers,
    )
    await client.post(f"/api/v1/invoices/{r1.json()['id']}/send", headers=headers)

    await client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id, "issue_date": "2026-01-01", "due_date": "2026-01-31",
            "line_items": [{"description": "Work 2", "quantity": 1, "unit_price": 100}],
        },
        headers=headers,
    )

    drafts = await client.get("/api/v1/invoices?status=draft", headers=headers)
    assert drafts.json()["total"] == 1
    sent = await client.get("/api/v1/invoices?status=sent", headers=headers)
    assert sent.json()["total"] == 1


async def test_deleting_invoice_releases_time_entries(client):
    headers, client_id = await _setup(client)
    p = await client.post(
        "/api/v1/projects", json={"name": "Release Project", "client_id": client_id, "hourly_rate": 100}, headers=headers
    )
    project_id = p.json()["id"]
    await client.post(
        "/api/v1/time-entries",
        json={"project_id": project_id, "started_at": "2026-01-01T09:00:00Z", "ended_at": "2026-01-01T10:00:00Z"},
        headers=headers,
    )
    gen = await client.post(
        "/api/v1/invoices/generate-from-time",
        json={"project_id": project_id, "issue_date": "2026-01-15", "due_date": "2026-02-15"},
        headers=headers,
    )
    invoice_id = gen.json()["id"]

    await client.delete(f"/api/v1/invoices/{invoice_id}", headers=headers)

    entries = await client.get(f"/api/v1/time-entries?project_id={project_id}", headers=headers)
    assert all(not e["is_invoiced"] for e in entries.json()["items"])


async def test_tenant_isolation_invoices(client):
    headers_a, client_a = await _setup(client, workspace_name="Tenant A")
    headers_b, _ = await _setup(client, workspace_name="Tenant B")

    resp = await client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_a, "issue_date": "2026-01-01", "due_date": "2026-01-31",
            "line_items": [{"description": "Secret", "quantity": 1, "unit_price": 999}],
        },
        headers=headers_a,
    )
    invoice_id = resp.json()["id"]

    cross = await client.get(f"/api/v1/invoices/{invoice_id}", headers=headers_b)
    assert cross.status_code == 404
