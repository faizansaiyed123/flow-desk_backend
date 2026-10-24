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


async def test_create_api_key_returns_plaintext_once(client):
    headers = await _setup(client)
    resp = await client.post("/api/v1/api-keys", json={"name": "CI integration"}, headers=headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["plaintext_key"].startswith("fd_live_")
    assert body["key_prefix"] == body["plaintext_key"][:12]


async def test_list_api_keys_never_exposes_plaintext(client):
    headers = await _setup(client)
    await client.post("/api/v1/api-keys", json={"name": "Key 1"}, headers=headers)
    listed = await client.get("/api/v1/api-keys", headers=headers)
    assert listed.status_code == 200
    assert "plaintext_key" not in listed.json()[0]
    assert "hashed_key" not in listed.json()[0]


async def test_api_key_can_authenticate_requests(client):
    headers = await _setup(client)
    created = await client.post("/api/v1/api-keys", json={"name": "External Tool"}, headers=headers)
    plaintext_key = created.json()["plaintext_key"]

    resp = await client.get("/api/v1/clients", headers={"Authorization": f"Bearer {plaintext_key}"})
    assert resp.status_code == 200


async def test_revoked_api_key_can_no_longer_authenticate(client):
    headers = await _setup(client)
    created = await client.post("/api/v1/api-keys", json={"name": "Temp Key"}, headers=headers)
    key_id = created.json()["id"]
    plaintext_key = created.json()["plaintext_key"]

    await client.delete(f"/api/v1/api-keys/{key_id}", headers=headers)

    resp = await client.get("/api/v1/clients", headers={"Authorization": f"Bearer {plaintext_key}"})
    assert resp.status_code == 401


async def test_api_key_respects_creators_current_role(client, db_session):
    """If the person who created the key is demoted below the role a route
    requires, the key should stop working for that route too — it's not an
    independent standing grant."""
    from app.models.membership import Membership, MembershipRole
    from app.models.user import User
    from app.security import create_token, hash_password

    headers = await _setup(client, workspace_name="RoleKeyCo")
    tenant_id = (await client.get("/api/v1/tenants/current", headers=headers)).json()["id"]

    admin_user = User(email=unique_email(), hashed_password=hash_password("pw12345678"), full_name="Admin Two")
    db_session.add(admin_user)
    await db_session.flush()
    membership = Membership(user_id=admin_user.id, tenant_id=tenant_id, role=MembershipRole.ADMIN)
    db_session.add(membership)
    await db_session.commit()
    admin_token = create_token(subject=str(admin_user.id), token_type="access", tenant_id=tenant_id)

    created = await client.post(
        "/api/v1/api-keys", json={"name": "Admin's Key"}, headers={"Authorization": f"Bearer {admin_token}"}
    )
    plaintext_key = created.json()["plaintext_key"]

    # Key works for an admin-gated action initially.
    ok = await client.post(
        "/api/v1/webhooks",
        json={"target_url": "https://example.com/hook", "events": ["invoice.sent"]},
        headers={"Authorization": f"Bearer {plaintext_key}"},
    )
    assert ok.status_code == 201

    # Demote the admin to member.
    membership.role = MembershipRole.MEMBER
    await db_session.commit()

    # Same key should now be denied for the admin-only action.
    denied = await client.post(
        "/api/v1/webhooks",
        json={"target_url": "https://example.com/hook2", "events": ["invoice.sent"]},
        headers={"Authorization": f"Bearer {plaintext_key}"},
    )
    assert denied.status_code == 403
