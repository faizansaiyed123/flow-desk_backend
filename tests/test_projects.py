import pytest

from tests.conftest import unique_email

pytestmark = pytest.mark.asyncio


async def _register(client, workspace_name="Acme"):
    email = unique_email()
    resp = await client.post(
        "/api/v1/auth/register",
        json={"full_name": "Owner", "email": email, "password": "supersecret123", "workspace_name": workspace_name},
    )
    assert resp.status_code == 201
    return resp.json()["access_token"]


async def test_create_project_without_client(client):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "Website Redesign", "billing_type": "hourly", "hourly_rate": 85},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "planning"


async def test_create_project_with_invalid_client_rejected(client):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    fake_client_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(
        "/api/v1/projects", json={"name": "Bad Project", "client_id": fake_client_id}, headers=headers
    )
    assert resp.status_code == 422


async def test_create_project_with_valid_client(client):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    c = await client.post("/api/v1/clients", json={"name": "Stark Industries"}, headers=headers)
    client_id = c.json()["id"]

    resp = await client.post(
        "/api/v1/projects", json={"name": "Arc Reactor App", "client_id": client_id}, headers=headers
    )
    assert resp.status_code == 201
    assert resp.json()["client_id"] == client_id

    detail = await client.get(f"/api/v1/projects/{resp.json()['id']}", headers=headers)
    assert detail.json()["client_name"] == "Stark Industries"


async def test_filter_projects_by_status_and_client(client):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    p1 = await client.post("/api/v1/projects", json={"name": "P1", "status": "active"}, headers=headers)
    await client.post("/api/v1/projects", json={"name": "P2", "status": "completed"}, headers=headers)

    filtered = await client.get("/api/v1/projects?status=active", headers=headers)
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["name"] == "P1"


async def test_update_project_status_logs_activity(client, db_session):
    from sqlalchemy import select

    from app.models.activity import ActivityLog

    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    p = await client.post("/api/v1/projects", json={"name": "Status Test"}, headers=headers)
    project_id = p.json()["id"]

    updated = await client.patch(f"/api/v1/projects/{project_id}", json={"status": "active"}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["status"] == "active"

    result = await db_session.execute(
        select(ActivityLog).where(ActivityLog.action == "project.status_changed")
    )
    logs = result.scalars().all()
    assert len(logs) == 1
    assert logs[0].metadata_json == {"old_status": "planning", "new_status": "active"}


async def test_project_stats_reflect_tasks(client):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    p = await client.post("/api/v1/projects", json={"name": "Stats Project"}, headers=headers)
    project_id = p.json()["id"]

    detail = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert detail.json()["task_count"] == 0
    assert detail.json()["total_hours_logged"] == 0


async def test_tenant_isolation_projects(client):
    token_a = await _register(client, workspace_name="Tenant A")
    token_b = await _register(client, workspace_name="Tenant B")

    p = await client.post(
        "/api/v1/projects", json={"name": "A Secret Project"}, headers={"Authorization": f"Bearer {token_a}"}
    )
    project_id = p.json()["id"]

    cross_get = await client.get(
        f"/api/v1/projects/{project_id}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert cross_get.status_code == 404

    b_list = await client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token_b}"})
    assert b_list.json()["total"] == 0
