import pytest

from tests.conftest import unique_email

pytestmark = pytest.mark.asyncio


async def test_register_creates_user_and_workspace_and_returns_tokens(client):
    email = unique_email()
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Ada Lovelace",
            "email": email,
            "password": "supersecret123",
            "workspace_name": "Ada Inc",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "access_token" in body and "refresh_token" in body


async def test_register_rejects_duplicate_email(client):
    email = unique_email()
    payload = {
        "full_name": "Ada",
        "email": email,
        "password": "supersecret123",
        "workspace_name": "Ada Inc",
    }
    r1 = await client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 409


async def test_register_rejects_weak_password(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Ada",
            "email": unique_email(),
            "password": "short",
            "workspace_name": "Ada Inc",
        },
    )
    assert resp.status_code == 422


async def test_login_with_correct_credentials_succeeds(client):
    email = unique_email()
    await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Grace Hopper",
            "email": email,
            "password": "supersecret123",
            "workspace_name": "Grace Co",
        },
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "supersecret123"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_login_with_wrong_password_fails(client):
    email = unique_email()
    await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Grace Hopper",
            "email": email,
            "password": "supersecret123",
            "workspace_name": "Grace Co",
        },
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrongpassword"})
    assert resp.status_code == 401


async def test_login_with_unknown_email_fails(client):
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@nowhere.com", "password": "whatever123"}
    )
    assert resp.status_code == 401


async def test_me_endpoint_requires_auth(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_endpoint_returns_user_and_memberships(client):
    email = unique_email()
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Ada Lovelace",
            "email": email,
            "password": "supersecret123",
            "workspace_name": "Ada Inc",
        },
    )
    token = reg.json()["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == email.lower()
    assert len(body["memberships"]) == 1
    assert body["memberships"][0]["role"] == "owner"


async def test_refresh_token_issues_new_access_token(client):
    email = unique_email()
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Ada",
            "email": email,
            "password": "supersecret123",
            "workspace_name": "Ada Inc",
        },
    )
    refresh_token = reg.json()["refresh_token"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_refresh_with_invalid_token_fails(client):
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 401


async def test_forgot_password_does_not_leak_whether_email_exists(client):
    resp1 = await client.post("/api/v1/auth/forgot-password", json={"email": "nobody@nowhere.com"})
    resp2 = await client.post("/api/v1/auth/forgot-password", json={"email": unique_email()})
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()


async def test_change_password_requires_correct_current_password(client):
    email = unique_email()
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Ada",
            "email": email,
            "password": "supersecret123",
            "workspace_name": "Ada Inc",
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    bad = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrongpass1", "new_password": "newpassword123"},
        headers=headers,
    )
    assert bad.status_code == 422

    good = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "supersecret123", "new_password": "newpassword123"},
        headers=headers,
    )
    assert good.status_code == 200

    relogin = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "newpassword123"}
    )
    assert relogin.status_code == 200
