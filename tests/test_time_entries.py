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
    return headers, project_id


async def test_create_manual_time_entry_with_duration(client):
    headers, project_id = await _setup(client)
    resp = await client.post(
        "/api/v1/time-entries",
        json={
            "project_id": project_id,
            "started_at": "2026-01-01T09:00:00Z",
            "duration_minutes": 90,
            "description": "Client call",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["duration_minutes"] == 90


async def test_create_manual_time_entry_computes_duration_from_end_time(client):
    headers, project_id = await _setup(client)
    resp = await client.post(
        "/api/v1/time-entries",
        json={
            "project_id": project_id,
            "started_at": "2026-01-01T09:00:00Z",
            "ended_at": "2026-01-01T11:30:00Z",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["duration_minutes"] == 150


async def test_time_entry_requires_end_or_duration(client):
    headers, project_id = await _setup(client)
    resp = await client.post(
        "/api/v1/time-entries",
        json={"project_id": project_id, "started_at": "2026-01-01T09:00:00Z"},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_end_before_start_rejected(client):
    headers, project_id = await _setup(client)
    resp = await client.post(
        "/api/v1/time-entries",
        json={
            "project_id": project_id,
            "started_at": "2026-01-01T09:00:00Z",
            "ended_at": "2026-01-01T08:00:00Z",
        },
        headers=headers,
    )
    assert resp.status_code == 422


async def test_start_and_stop_timer(client):
    headers, project_id = await _setup(client)
    started = await client.post("/api/v1/time-entries/timer/start", json={"project_id": project_id}, headers=headers)
    assert started.status_code == 201
    assert started.json()["ended_at"] is None

    running = await client.get("/api/v1/time-entries/timer/running", headers=headers)
    assert running.status_code == 200
    assert running.json() is not None
    assert running.json()["id"] == started.json()["id"]

    stopped = await client.post("/api/v1/time-entries/timer/stop", headers=headers)
    assert stopped.status_code == 200
    assert stopped.json()["ended_at"] is not None
    assert stopped.json()["duration_minutes"] is not None

    no_longer_running = await client.get("/api/v1/time-entries/timer/running", headers=headers)
    assert no_longer_running.json() is None


async def test_cannot_start_second_timer_while_one_running(client):
    headers, project_id = await _setup(client)
    r1 = await client.post("/api/v1/time-entries/timer/start", json={"project_id": project_id}, headers=headers)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/time-entries/timer/start", json={"project_id": project_id}, headers=headers)
    assert r2.status_code == 409


async def test_stop_timer_with_none_running_returns_404(client):
    headers, _ = await _setup(client)
    resp = await client.post("/api/v1/time-entries/timer/stop", headers=headers)
    assert resp.status_code == 404


async def test_list_and_filter_time_entries(client):
    headers, project_id = await _setup(client)
    await client.post(
        "/api/v1/time-entries",
        json={"project_id": project_id, "started_at": "2026-01-01T09:00:00Z", "duration_minutes": 60, "is_billable": True},
        headers=headers,
    )
    await client.post(
        "/api/v1/time-entries",
        json={"project_id": project_id, "started_at": "2026-01-02T09:00:00Z", "duration_minutes": 30, "is_billable": False},
        headers=headers,
    )

    listed = await client.get(f"/api/v1/time-entries?project_id={project_id}", headers=headers)
    assert listed.json()["total"] == 2


async def test_update_time_entry_recomputes_duration(client):
    headers, project_id = await _setup(client)
    r = await client.post(
        "/api/v1/time-entries",
        json={"project_id": project_id, "started_at": "2026-01-01T09:00:00Z", "duration_minutes": 60},
        headers=headers,
    )
    entry_id = r.json()["id"]

    updated = await client.patch(
        f"/api/v1/time-entries/{entry_id}",
        json={"ended_at": "2026-01-01T12:00:00Z"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["duration_minutes"] == 180


async def test_delete_time_entry(client):
    headers, project_id = await _setup(client)
    r = await client.post(
        "/api/v1/time-entries",
        json={"project_id": project_id, "started_at": "2026-01-01T09:00:00Z", "duration_minutes": 60},
        headers=headers,
    )
    entry_id = r.json()["id"]
    deleted = await client.delete(f"/api/v1/time-entries/{entry_id}", headers=headers)
    assert deleted.status_code == 200


async def test_user_cannot_edit_another_users_time_entry(client, db_session):
    from app.models.membership import Membership, MembershipRole
    from app.models.user import User
    from app.security import create_token, hash_password

    headers, project_id = await _setup(client, workspace_name="SharedCo")
    me = await client.get("/api/v1/auth/me", headers=headers)
    me_tenant = (await client.get("/api/v1/tenants/current", headers=headers)).json()["id"]

    r = await client.post(
        "/api/v1/time-entries",
        json={"project_id": project_id, "started_at": "2026-01-01T09:00:00Z", "duration_minutes": 60},
        headers=headers,
    )
    entry_id = r.json()["id"]

    teammate = User(email=unique_email(), hashed_password=hash_password("pw12345678"), full_name="Team Mate")
    db_session.add(teammate)
    await db_session.flush()
    db_session.add(Membership(user_id=teammate.id, tenant_id=me_tenant, role=MembershipRole.MEMBER))
    await db_session.commit()
    teammate_token = create_token(subject=str(teammate.id), token_type="access", tenant_id=me_tenant)

    forbidden = await client.patch(
        f"/api/v1/time-entries/{entry_id}",
        json={"description": "hijacked"},
        headers={"Authorization": f"Bearer {teammate_token}"},
    )
    assert forbidden.status_code == 422
