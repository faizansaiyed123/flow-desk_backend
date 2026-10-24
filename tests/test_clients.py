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


async def test_create_and_get_client(client):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/clients",
        json={"name": "Wayne Enterprises", "company": "Wayne Ent.", "email": "bruce@wayne.com"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    client_id = resp.json()["id"]

    get_resp = await client.get(f"/api/v1/clients/{client_id}", headers=headers)
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["name"] == "Wayne Enterprises"
    assert body["project_count"] == 0


async def test_list_clients_search_and_pagination(client):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}

    for name in ["Alpha Corp", "Beta LLC", "Gamma Inc"]:
        r = await client.post("/api/v1/clients", json={"name": name}, headers=headers)
        assert r.status_code == 201

    listed = await client.get("/api/v1/clients", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 3

    searched = await client.get("/api/v1/clients?search=beta", headers=headers)
    assert searched.status_code == 200
    assert searched.json()["total"] == 1
    assert searched.json()["items"][0]["name"] == "Beta LLC"

    paged = await client.get("/api/v1/clients?page=1&page_size=2", headers=headers)
    assert len(paged.json()["items"]) == 2
    assert paged.json()["total_pages"] == 2


async def test_archived_clients_excluded_by_default(client):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.post("/api/v1/clients", json={"name": "Old Client"}, headers=headers)
    client_id = r.json()["id"]

    await client.patch(f"/api/v1/clients/{client_id}", json={"is_archived": True}, headers=headers)

    default_list = await client.get("/api/v1/clients", headers=headers)
    assert default_list.json()["total"] == 0

    with_archived = await client.get("/api/v1/clients?include_archived=true", headers=headers)
    assert with_archived.json()["total"] == 1


async def test_update_client(client):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.post("/api/v1/clients", json={"name": "Initial Name"}, headers=headers)
    client_id = r.json()["id"]

    updated = await client.patch(
        f"/api/v1/clients/{client_id}", json={"name": "Updated Name", "notes": "VIP client"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Name"
    assert updated.json()["notes"] == "VIP client"


async def test_delete_client_requires_admin_role(client, db_session):
    from app.models.membership import Membership, MembershipRole
    from app.models.user import User
    from app.security import create_token, hash_password

    token = await _register(client, workspace_name="DeleteCo")
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.post("/api/v1/clients", json={"name": "ToDelete"}, headers=headers)
    client_id = r.json()["id"]

    me = await client.get("/api/v1/tenants/current", headers=headers)
    tenant_id = me.json()["id"]

    plain_member = User(email=unique_email(), hashed_password=hash_password("pw12345678"), full_name="Mem Ber")
    db_session.add(plain_member)
    await db_session.flush()
    db_session.add(Membership(user_id=plain_member.id, tenant_id=tenant_id, role=MembershipRole.MEMBER))
    await db_session.commit()
    member_token = create_token(subject=str(plain_member.id), token_type="access", tenant_id=tenant_id)

    forbidden = await client.delete(
        f"/api/v1/clients/{client_id}", headers={"Authorization": f"Bearer {member_token}"}
    )
    assert forbidden.status_code == 403

    allowed = await client.delete(f"/api/v1/clients/{client_id}", headers=headers)
    assert allowed.status_code == 200


async def test_tenant_isolation_cannot_access_other_tenants_client(client):
    """The core multi-tenancy guarantee: tenant A can never read/write
    tenant B's data, even with a valid, well-formed token."""
    token_a = await _register(client, workspace_name="Tenant A")
    token_b = await _register(client, workspace_name="Tenant B")

    r = await client.post(
        "/api/v1/clients", json={"name": "A's Secret Client"}, headers={"Authorization": f"Bearer {token_a}"}
    )
    client_id = r.json()["id"]

    cross_tenant_get = await client.get(
        f"/api/v1/clients/{client_id}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert cross_tenant_get.status_code == 404

    cross_tenant_update = await client.patch(
        f"/api/v1/clients/{client_id}", json={"name": "Hijacked"}, headers={"Authorization": f"Bearer {token_b}"}
    )
    assert cross_tenant_update.status_code == 404

    cross_tenant_delete = await client.delete(
        f"/api/v1/clients/{client_id}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert cross_tenant_delete.status_code == 404

    # And B's client list must never include A's client.
    b_list = await client.get("/api/v1/clients", headers={"Authorization": f"Bearer {token_b}"})
    assert all(c["id"] != client_id for c in b_list.json()["items"])
