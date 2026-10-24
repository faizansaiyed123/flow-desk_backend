import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID | None
    project_id: uuid.UUID | None
    uploaded_by_id: uuid.UUID
    file_name: str
    content_type: str
    size_bytes: int
    created_at: datetime
