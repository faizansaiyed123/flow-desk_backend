import pytest
from httpx import ASGITransport, AsyncClient

from demo_app import app, reset_demo_state

@pytest.fixture
async def client():
    reset_demo_state()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

async def login(client: AsyncClient, email: str = "alex@northstar.demo"):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Demo1234!"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

async def test_health_and_seeded_workspace(client):
    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["environment"] == "in-memory-demo"

    headers = await login(client)
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "alex@northstar.demo"
    assert len(me.json()["memberships"]) == 2

    tenant = await client.get("/api/v1/tenants/current", headers=headers)
    assert tenant.json()["name"] == "Northstar Creative"

async def test_workspace_switching_keeps_tenant_data_separate(client):
    headers = await login(client)
    created = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": "Private Northstar project", "status": "active"},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    switched = await client.post(
        "/api/v1/auth/switch-tenant",
        headers=headers,
        json={"tenant_id": "tenant_flowdesk_labs"},
    )
    assert switched.status_code == 200
    labs_headers = {"Authorization": f"Bearer {switched.json()['access_token']}"}

    not_found = await client.get(f"/api/v1/projects/{project_id}", headers=labs_headers)
    assert not_found.status_code == 404
    clients = await client.get("/api/v1/clients", headers=labs_headers)
    assert clients.status_code == 200
    assert [item["name"] for item in clients.json()["items"]] == ["Prototype Partners"]

async def test_kanban_task_update_and_comments(client):
    headers = await login(client)
    board = await client.get("/api/v1/tasks/board/project_brand", headers=headers)
    assert board.status_code == 200
    assert {column["status"] for column in board.json()["columns"]} == {
        "backlog", "todo", "in_progress", "in_review", "done"
    }

    created = await client.post(
        "/api/v1/tasks",
        headers=headers,
        json={
            "project_id": "project_brand",
            "title": "Prepare recruiter demo handoff",
            "status": "todo",
            "priority": "high",
        },
    )
    assert created.status_code == 201
    task_id = created.json()["id"]

    moved = await client.patch(
        f"/api/v1/tasks/{task_id}/move",
        headers=headers,
        json={"status": "done", "position": 450},
    )
    assert moved.status_code == 200
    assert moved.json()["status"] == "done"
    assert moved.json()["completed_at"]

    comment = await client.post(
        f"/api/v1/tasks/{task_id}/comments",
        headers=headers,
        json={"body": "Handoff reviewed and approved."},
    )
    assert comment.status_code == 201
    comments = await client.get(f"/api/v1/tasks/{task_id}/comments", headers=headers)
    assert comments.json()[0]["body"] == "Handoff reviewed and approved."

async def test_unbilled_time_generates_invoice_and_marks_entries_invoiced(client):
    headers = await login(client)
    created = await client.post(
        "/api/v1/time-entries",
        headers=headers,
        json={
            "project_id": "project_brand",
            "task_id": "task_guidelines",
            "started_at": "2026-11-15T09:00:00+00:00",
            "ended_at": "2026-11-15T11:30:00+00:00",
            "duration_minutes": 150,
            "description": "Final brand guidelines review",
            "is_billable": True,
        },
    )
    assert created.status_code == 201

    generated = await client.post(
        "/api/v1/invoices/generate-from-time",
        headers=headers,
        json={
            "project_id": "project_brand",
            "issue_date": "2026-11-16",
            "due_date": "2026-12-16",
            "tax_rate": 0,
        },
    )
    assert generated.status_code == 201, generated.text
    invoice = generated.json()
    assert invoice["status"] == "draft"
    assert invoice["total"] > 0
    assert len(invoice["line_items"]) == 1

    entries = await client.get(
        "/api/v1/time-entries",
        headers=headers,
        params={"project_id": "project_brand"},
    )
    assert all(entry["is_invoiced"] for entry in entries.json()["items"])

    sent = await client.post(f"/api/v1/invoices/{invoice['id']}/send", headers=headers)
    assert sent.status_code == 200
    paid = await client.post(f"/api/v1/invoices/{invoice['id']}/mark-paid", headers=headers)
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"

async def test_role_boundaries_are_enforced_in_demo_api(client):
    member_headers = await login(client, "sam@northstar.demo")
    forbidden_invoice = await client.post(
        "/api/v1/invoices",
        headers=member_headers,
        json={
            "client_id": "client_aperture",
            "line_items": [{"description": "Work", "quantity": 1, "unit_price": 100}],
        },
    )
    assert forbidden_invoice.status_code == 403

    viewer_headers = await login(client, "taylor@northstar.demo")
    forbidden_task = await client.post(
        "/api/v1/tasks",
        headers=viewer_headers,
        json={"project_id": "project_brand", "title": "Viewer cannot create this"},
    )
    assert forbidden_task.status_code == 403
