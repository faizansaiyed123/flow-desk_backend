import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.membership import MembershipRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    avatar_url: str | None
    is_email_verified: bool
    created_at: datetime


class MembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MembershipRole
    tenant_id: uuid.UUID
    user: UserOut


class TenantSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    logo_url: str | None
    plan: str


class MeResponse(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]
    current_tenant: TenantSummary | None = None
    current_role: MembershipRole | None = None


class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    avatar_url: str | None = None


class UpdateMemberRoleRequest(BaseModel):
    role: MembershipRole


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    membership_id: uuid.UUID
    user: UserOut
    role: MembershipRole
    joined_at: datetime
