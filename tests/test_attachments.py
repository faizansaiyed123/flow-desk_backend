import io

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
    p = await client.post("/api/v1/projects", json={"name": "Files Project"}, headers=headers)
    return headers, p.json()["id"]


def _patch_upload_dir(monkeypatch, tmp_path):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    import app.services.attachment_service as attachment_service_module
    attachment_service_module.settings = get_settings()


async def test_upload_and_download_attachment(client, tmp_path, monkeypatch):
    _patch_upload_dir(monkeypatch, tmp_path)
    headers, project_id = await _setup(client)
    file_content = b"hello world, this is a test file"
    resp = await client.post(
        "/api/v1/attachments",
        params={"project_id": project_id},
        files={"file": ("notes.txt", io.BytesIO(file_content), "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    attachment_id = resp.json()["id"]
    assert resp.json()["file_name"] == "notes.txt"
    assert resp.json()["size_bytes"] == len(file_content)

    download = await client.get(f"/api/v1/attachments/{attachment_id}/download", headers=headers)
    assert download.status_code == 200
    assert download.content == file_content


async def test_upload_rejects_disallowed_extension(client, tmp_path, monkeypatch):
    _patch_upload_dir(monkeypatch, tmp_path)
    headers, project_id = await _setup(client)
    resp = await client.post(
        "/api/v1/attachments",
        params={"project_id": project_id},
        files={"file": ("script.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_attachment_requires_task_or_project(client, tmp_path, monkeypatch):
    _patch_upload_dir(monkeypatch, tmp_path)
    headers, _ = await _setup(client)
    resp = await client.post(
        "/api/v1/attachments",
        files={"file": ("notes.txt", io.BytesIO(b"hi"), "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_list_and_delete_attachment(client, tmp_path, monkeypatch):
    _patch_upload_dir(monkeypatch, tmp_path)
    headers, project_id = await _setup(client)
    uploaded = await client.post(
        "/api/v1/attachments",
        params={"project_id": project_id},
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        headers=headers,
    )
    attachment_id = uploaded.json()["id"]

    listed = await client.get(f"/api/v1/attachments?project_id={project_id}", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = await client.delete(f"/api/v1/attachments/{attachment_id}", headers=headers)
    assert deleted.status_code == 200

    listed_after = await client.get(f"/api/v1/attachments?project_id={project_id}", headers=headers)
    assert len(listed_after.json()) == 0
