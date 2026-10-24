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
    return {"Authorization": f"Bearer {token}"}


async def test_activity_feed_records_actions(client):
    headers = await _setup(client)
    c = await client.post("/api/v1/clients", json={"name": "Feed Client"}, headers=headers)
    p = await client.post("/api/v1/projects", json={"name": "Feed Project", "client_id": c.json()["id"]}, headers=headers)

    feed = await client.get("/api/v1/activity", headers=headers)
    assert feed.status_code == 200
    actions = [entry["action"] for entry in feed.json()]
    assert "workspace.created" in actions
    assert "client.created" in actions
    assert "project.created" in actions


async def test_activity_feed_can_filter_by_entity(client):
    headers = await _setup(client)
    c1 = await client.post("/api/v1/clients", json={"name": "Client A"}, headers=headers)
    await client.post("/api/v1/clients", json={"name": "Client B"}, headers=headers)

    filtered = await client.get(
        f"/api/v1/activity?entity_type=client&entity_id={c1.json()['id']}", headers=headers
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["entity_label"] == "Client A"


async def test_dashboard_summary_reflects_real_data(client):
    headers = await _setup(client)
    c = await client.post("/api/v1/clients", json={"name": "Dash Client"}, headers=headers)
    p = await client.post(
        "/api/v1/projects",
        json={"name": "Dash Project", "client_id": c.json()["id"], "status": "active"},
        headers=headers,
    )
    project_id = p.json()["id"]
    await client.post("/api/v1/tasks", json={"project_id": project_id, "title": "Task 1", "status": "done"}, headers=headers)
    await client.post("/api/v1/tasks", json={"project_id": project_id, "title": "Task 2"}, headers=headers)

    summary = await client.get("/api/v1/dashboard/summary", headers=headers)
    assert summary.status_code == 200
    body = summary.json()
    assert body["active_project_count"] == 1
    assert body["total_client_count"] == 1
    assert body["total_task_count"] == 2
    assert len(body["project_health"]) == 1
    assert body["project_health"][0]["task_count"] == 2
    assert body["project_health"][0]["completed_task_count"] == 1
    assert body["project_health"][0]["percent_complete"] == 50.0
    assert len(body["revenue_by_month"]) == 6


async def test_search_finds_clients_projects_and_tasks(client):
    headers = await _setup(client)
    await client.post("/api/v1/clients", json={"name": "Searchable Client Corp"}, headers=headers)
    p = await client.post("/api/v1/projects", json={"name": "Searchable Project"}, headers=headers)
    await client.post(
        "/api/v1/tasks", json={"project_id": p.json()["id"], "title": "Searchable Task"}, headers=headers
    )

    resp = await client.get("/api/v1/search?q=searchable", headers=headers)
    assert resp.status_code == 200
    types = {r["type"] for r in resp.json()["results"]}
    assert types == {"client", "project", "task"}


async def test_search_query_too_short_returns_empty(client):
    headers = await _setup(client)
    resp = await client.get("/api/v1/search?q=a", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["results"] == []


async def test_search_isolated_by_tenant(client):
    headers_a = await _setup(client, workspace_name="Tenant A")
    headers_b = await _setup(client, workspace_name="Tenant B")

    await client.post("/api/v1/clients", json={"name": "UniqueSearchTermXYZ"}, headers=headers_a)

    found_a = await client.get("/api/v1/search?q=uniquesearchtermxyz", headers=headers_a)
    assert len(found_a.json()["results"]) == 1

    found_b = await client.get("/api/v1/search?q=uniquesearchtermxyz", headers=headers_b)
    assert len(found_b.json()["results"]) == 0
