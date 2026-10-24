import pytest

from tests.conftest import unique_email

pytestmark = pytest.mark.asyncio


async def test_task_assignment_creates_notification_for_assignee(client, db_session):
    from sqlalchemy import select

    from app.models.membership import Membership, MembershipRole
    from app.models.user import User
    from app.security import create_token, hash_password

    owner_email = unique_email()
    reg = await client.post(
        "/api/v1/auth/register",
        json={"full_name": "Owner", "email": owner_email, "password": "supersecret123", "workspace_name": "NotifyCo"},
    )
    owner_token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {owner_token}"}

    me = await client.get("/api/v1/tenants/current", headers=headers)
    tenant_id = me.json()["id"]

    teammate = User(email=unique_email(), hashed_password=hash_password("pw12345678"), full_name="Team Mate")
    db_session.add(teammate)
    await db_session.flush()
    db_session.add(Membership(user_id=teammate.id, tenant_id=tenant_id, role=MembershipRole.MEMBER))
    await db_session.commit()

    p = await client.post("/api/v1/projects", json={"name": "Notify Project"}, headers=headers)
    project_id = p.json()["id"]

    await client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Assigned task", "assignee_id": str(teammate.id)},
        headers=headers,
    )

    teammate_token = create_token(subject=str(teammate.id), token_type="access", tenant_id=tenant_id)
    teammate_headers = {"Authorization": f"Bearer {teammate_token}"}

    notifications = await client.get("/api/v1/notifications", headers=teammate_headers)
    assert notifications.status_code == 200
    assert notifications.json()["total"] == 1
    assert "Assigned task" in notifications.json()["items"][0]["title"]
    assert notifications.json()["items"][0]["link"] == f"/app/projects/{project_id}"

    unread = await client.get("/api/v1/notifications/unread-count", headers=teammate_headers)
    assert unread.json()["count"] == 1

    notif_id = notifications.json()["items"][0]["id"]
    marked = await client.post(f"/api/v1/notifications/{notif_id}/read", headers=teammate_headers)
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True

    unread_after = await client.get("/api/v1/notifications/unread-count", headers=teammate_headers)
    assert unread_after.json()["count"] == 0


async def test_mark_all_read(client, db_session):
    from app.models.membership import Membership, MembershipRole
    from app.models.notification import NotificationType
    from app.services import notification_service

    owner_email = unique_email()
    reg = await client.post(
        "/api/v1/auth/register",
        json={"full_name": "Owner", "email": owner_email, "password": "supersecret123", "workspace_name": "MarkAllCo"},
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/v1/tenants/current", headers=headers)
    tenant_id = me.json()["id"]
    user_id = reg.json()  # not directly available; fetch via /auth/me
    me_resp = await client.get("/api/v1/auth/me", headers=headers)
    user_id = me_resp.json()["user"]["id"]

    import uuid as uuid_module

    for i in range(3):
        await notification_service.create_notification(
            db_session, tenant_id=uuid_module.UUID(tenant_id), user_id=uuid_module.UUID(user_id),
            type=NotificationType.MENTION, title=f"Notice {i}",
        )
    await db_session.commit()

    resp = await client.post("/api/v1/notifications/read-all", headers=headers)
    assert resp.status_code == 200

    unread = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert unread.json()["count"] == 0
