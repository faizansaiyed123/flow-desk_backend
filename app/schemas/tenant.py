import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.invitation import InvitationStatus
from app.models.membership import MembershipRole


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    logo_url: str | None
    plan: str
    is_active: bool
    created_at: datetime


class UpdateTenantRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    logo_url: str | None = None


class CreateInvitationRequest(BaseModel):
    email: EmailStr
    role: MembershipRole = MembershipRole.MEMBER

    @field_validator("role")
    @classmethod
    def cannot_invite_owner(cls, v: MembershipRole) -> MembershipRole:
        if v == MembershipRole.OWNER:
            raise ValueError("Cannot invite someone directly as owner. Promote them after they join.")
        return v


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: MembershipRole
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime


class InvitationPreview(BaseModel):
    """Public-safe preview shown on the accept-invite page before login."""

    tenant_name: str
    email: str
    role: MembershipRole
    is_new_user: bool
