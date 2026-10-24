import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.config import get_settings

settings = get_settings()


class RegisterRequest(BaseModel):
    """Registering creates a User AND their first Tenant (workspace) in one
    step — the standard "sign up and get a workspace" SaaS onboarding flow."""

    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str
    workspace_name: str = Field(min_length=1, max_length=120)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < settings.PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters.")
        if v.isalpha() or v.isdigit():
            raise ValueError("Password must contain a mix of letters and numbers.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_id: uuid.UUID | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class SwitchTenantRequest(BaseModel):
    tenant_id: uuid.UUID


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < settings.PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters.")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < settings.PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters.")
        return v


class AcceptInvitationRequest(BaseModel):
    token: str
    full_name: str | None = Field(default=None, max_length=120)
    password: str | None = None
