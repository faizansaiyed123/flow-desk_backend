import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext
from app.database import get_db
from app.dependencies import get_auth_context, require_role
from app.models.membership import MembershipRole
from app.schemas.attachment import AttachmentOut
from app.schemas.common import MessageResponse
from app.services import attachment_service

router = APIRouter()


@router.post("", response_model=AttachmentOut, status_code=201)
async def upload_attachment(
    file: UploadFile = File(...),
    task_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    attachment = await attachment_service.save_attachment(
        db, tenant_id=ctx.tenant_id, uploaded_by_id=ctx.user.id, file_name=file.filename,
        content_type=file.content_type or "application/octet-stream", content=content,
        task_id=task_id, project_id=project_id,
    )
    return AttachmentOut.model_validate(attachment)


@router.get("", response_model=list[AttachmentOut])
async def list_attachments(
    task_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    attachments = await attachment_service.list_attachments(
        db, tenant_id=ctx.tenant_id, task_id=task_id, project_id=project_id
    )
    return [AttachmentOut.model_validate(a) for a in attachments]


@router.get("/{attachment_id}/download")
async def download_attachment(
    attachment_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)
):
    attachment = await attachment_service.get_attachment(db, tenant_id=ctx.tenant_id, attachment_id=attachment_id)
    content = attachment_service.read_file(attachment)
    return Response(
        content=content, media_type=attachment.content_type,
        headers={"Content-Disposition": f'attachment; filename="{attachment.file_name}"'},
    )


@router.delete("/{attachment_id}", response_model=MessageResponse)
async def delete_attachment(
    attachment_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(MembershipRole.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    await attachment_service.delete_attachment(
        db, tenant_id=ctx.tenant_id, actor_id=ctx.user.id, attachment_id=attachment_id
    )
    return MessageResponse(message="Attachment deleted.")
