"""File attachment storage.

Storage is local disk under UPLOAD_DIR, laid out as
`{UPLOAD_DIR}/{tenant_id}/{attachment_id}{ext}` so tenants can never collide
or traverse into each other's files by guessing paths. This is intentionally
a small, swappable boundary — swapping to S3/GCS later means changing
`save_file`/`read_file`/`delete_file` here, nothing else in the app.
"""
import os
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.attachment import Attachment
from app.services import activity_service
from app.services.project_service import get_project
from app.services.task_service import get_task

settings = get_settings()


def _tenant_dir(tenant_id: uuid.UUID) -> Path:
    path = Path(settings.UPLOAD_DIR) / str(tenant_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _validate_upload(*, file_name: str, size_bytes: int) -> None:
    # Strip any directory traversal / control characters from the stored
    # display name — the on-disk path is already a UUID, but a malicious
    # filename (../../etc/passwd) is still stored verbatim in the DB and
    # shown back to clients, which is a stored-XSS / traversal vector.
    sanitized = file_name.strip().replace("/", "_").replace("\\", "_").replace("\0", "")
    if not sanitized or sanitized != file_name:
        raise ValidationError("File name contains invalid characters.")
    ext = Path(file_name).suffix.lower()
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise ValidationError(f"File type '{ext}' is not allowed.")
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        raise ValidationError(f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB upload limit.")


async def save_attachment(
    db: AsyncSession, *, tenant_id: uuid.UUID, uploaded_by_id: uuid.UUID, file_name: str,
    content_type: str, content: bytes, task_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None,
) -> Attachment:
    if not task_id and not project_id:
        raise ValidationError("An attachment must be linked to either a task or a project.")
    if task_id:
        await get_task(db, tenant_id=tenant_id, task_id=task_id)
    if project_id:
        await get_project(db, tenant_id=tenant_id, project_id=project_id)

    _validate_upload(file_name=file_name, size_bytes=len(content))

    attachment_id = uuid.uuid4()
    ext = Path(file_name).suffix.lower()
    storage_path = _tenant_dir(tenant_id) / f"{attachment_id}{ext}"
    storage_path.write_bytes(content)

    attachment = Attachment(
        id=attachment_id, tenant_id=tenant_id, task_id=task_id, project_id=project_id,
        uploaded_by_id=uploaded_by_id, file_name=file_name, storage_path=str(storage_path),
        content_type=content_type, size_bytes=len(content),
    )
    db.add(attachment)
    await db.flush()

    await activity_service.log_activity(
        db, tenant_id=tenant_id, actor_id=uploaded_by_id, action="attachment.uploaded",
        entity_type="attachment", entity_id=attachment.id, entity_label=file_name,
    )
    return attachment


async def get_attachment(db: AsyncSession, *, tenant_id: uuid.UUID, attachment_id: uuid.UUID) -> Attachment:
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.tenant_id == tenant_id)
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise NotFoundError("Attachment not found.")
    return attachment


async def list_attachments(
    db: AsyncSession, *, tenant_id: uuid.UUID, task_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None,
) -> list[Attachment]:
    stmt = select(Attachment).where(Attachment.tenant_id == tenant_id)
    if task_id:
        stmt = stmt.where(Attachment.task_id == task_id)
    if project_id:
        stmt = stmt.where(Attachment.project_id == project_id)
    stmt = stmt.order_by(Attachment.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


def read_file(attachment: Attachment) -> bytes:
    return Path(attachment.storage_path).read_bytes()


async def delete_attachment(db: AsyncSession, *, tenant_id: uuid.UUID, attachment_id: uuid.UUID) -> None:
    attachment = await get_attachment(db, tenant_id=tenant_id, attachment_id=attachment_id)
    try:
        os.remove(attachment.storage_path)
    except FileNotFoundError:
        pass
    await db.delete(attachment)
    await db.flush()
