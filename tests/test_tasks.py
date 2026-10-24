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
    p = await client.post("/api/v1/projects", json={"name": "Test Project"}, headers=headers)
    project_id = p.json()["id"]
    return headers, project_id, token


async def test_create_task_defaults_to_todo(client):
    headers, project_id, _ = await _setup(client)
    resp = await client.post(
        "/api/v1/tasks", json={"project_id": project_id, "title": "Design homepage"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "todo"
    assert resp.json()["position"] > 0


async def test_create_task_invalid_project_rejected(client):
    headers, _, _ = await _setup(client)
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.post("/api/v1/tasks", json={"project_id": fake_id, "title": "Ghost task"}, headers=headers)
    assert resp.status_code == 422


async def test_assignee_must_be_workspace_member(client):
    headers, project_id, _ = await _setup(client)
    fake_user_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Assigned task", "assignee_id": fake_user_id},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_kanban_board_groups_tasks_by_status_in_order(client):
    headers, project_id, _ = await _setup(client)
    titles_and_status = [("Backlog item", "backlog"), ("Todo item", "todo"), ("Doing item", "in_progress")]
    for title, status in titles_and_status:
        r = await client.post(
            "/api/v1/tasks", json={"project_id": project_id, "title": title, "status": status}, headers=headers
        )
        assert r.status_code == 201

    board = await client.get(f"/api/v1/tasks/board/{project_id}", headers=headers)
    assert board.status_code == 200
    columns = {c["status"]: c["tasks"] for c in board.json()["columns"]}
    assert len(columns["backlog"]) == 1
    assert len(columns["todo"]) == 1
    assert len(columns["in_progress"]) == 1
    assert len(columns["done"]) == 0


async def test_new_tasks_in_same_column_get_increasing_positions(client):
    headers, project_id, _ = await _setup(client)
    r1 = await client.post("/api/v1/tasks", json={"project_id": project_id, "title": "First"}, headers=headers)
    r2 = await client.post("/api/v1/tasks", json={"project_id": project_id, "title": "Second"}, headers=headers)
    assert r2.json()["position"] > r1.json()["position"]


async def test_move_task_between_columns_updates_status_and_position(client):
    headers, project_id, _ = await _setup(client)
    r = await client.post("/api/v1/tasks", json={"project_id": project_id, "title": "Movable"}, headers=headers)
    task_id = r.json()["id"]

    moved = await client.patch(
        f"/api/v1/tasks/{task_id}/move", json={"status": "in_progress", "position": 500.0}, headers=headers
    )
    assert moved.status_code == 200
    assert moved.json()["status"] == "in_progress"
    assert moved.json()["position"] == 500.0


async def test_moving_task_to_done_sets_completed_at_and_back_clears_it(client):
    headers, project_id, _ = await _setup(client)
    r = await client.post("/api/v1/tasks", json={"project_id": project_id, "title": "Finishable"}, headers=headers)
    task_id = r.json()["id"]

    done = await client.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"}, headers=headers)
    assert done.json()["completed_at"] is not None

    reopened = await client.patch(f"/api/v1/tasks/{task_id}", json={"status": "todo"}, headers=headers)
    assert reopened.json()["completed_at"] is None


async def test_add_and_list_comments(client):
    headers, project_id, _ = await _setup(client)
    r = await client.post("/api/v1/tasks", json={"project_id": project_id, "title": "Commentable"}, headers=headers)
    task_id = r.json()["id"]

    c1 = await client.post(f"/api/v1/tasks/{task_id}/comments", json={"body": "First comment"}, headers=headers)
    assert c1.status_code == 201
    c2 = await client.post(f"/api/v1/tasks/{task_id}/comments", json={"body": "Second comment"}, headers=headers)
    assert c2.status_code == 201

    listed = await client.get(f"/api/v1/tasks/{task_id}/comments", headers=headers)
    assert listed.status_code == 200
    bodies = [c["body"] for c in listed.json()]
    assert bodies == ["First comment", "Second comment"]


async def test_delete_task(client):
    headers, project_id, _ = await _setup(client)
    r = await client.post("/api/v1/tasks", json={"project_id": project_id, "title": "Deletable"}, headers=headers)
    task_id = r.json()["id"]

    deleted = await client.delete(f"/api/v1/tasks/{task_id}", headers=headers)
    assert deleted.status_code == 200

    gone = await client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert gone.status_code == 404


async def test_filter_tasks_by_status_and_search(client):
    headers, project_id, _ = await _setup(client)
    await client.post("/api/v1/tasks", json={"project_id": project_id, "title": "Fix login bug", "status": "todo"}, headers=headers)
    await client.post("/api/v1/tasks", json={"project_id": project_id, "title": "Write docs", "status": "done"}, headers=headers)

    by_status = await client.get(f"/api/v1/tasks?project_id={project_id}&status=done", headers=headers)
    assert by_status.json()["total"] == 1
    assert by_status.json()["items"][0]["title"] == "Write docs"

    by_search = await client.get(f"/api/v1/tasks?project_id={project_id}&search=login", headers=headers)
    assert by_search.json()["total"] == 1


async def test_tenant_isolation_tasks(client):
    headers_a, project_a, _ = await _setup(client, workspace_name="Tenant A")
    headers_b, project_b, _ = await _setup(client, workspace_name="Tenant B")

    r = await client.post("/api/v1/tasks", json={"project_id": project_a, "title": "A's task"}, headers=headers_a)
    task_id = r.json()["id"]

    cross = await client.get(f"/api/v1/tasks/{task_id}", headers=headers_b)
    assert cross.status_code == 404

    cross_board = await client.get(f"/api/v1/tasks/board/{project_a}", headers=headers_b)
    assert cross_board.status_code == 404
