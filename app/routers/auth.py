from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SwitchTenantRequest,
    TokenPair,
)
from app.schemas.common import MessageResponse
from app.schemas.user import MeResponse, MembershipOut, TenantSummary, UserOut
from app.services import auth_service

router = APIRouter()


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user, tenant, membership = await auth_service.register(
        db,
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
        workspace_name=payload.workspace_name,
    )
    from app.security import create_token

    access = create_token(subject=str(user.id), token_type="access", tenant_id=str(tenant.id))
    refresh = create_token(subject=str(user.id), token_type="refresh", tenant_id=str(tenant.id))
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    _, _, _, access, refresh = await auth_service.login(
        db, email=payload.email, password=payload.password, tenant_id=payload.tenant_id
    )
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    access, refresh_token = await auth_service.refresh_tokens(db, refresh_token=payload.refresh_token)
    return TokenPair(access_token=access, refresh_token=refresh_token)


@router.post("/switch-tenant", response_model=TokenPair)
async def switch_tenant(
    payload: SwitchTenantRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    access, refresh, _role = await auth_service.switch_tenant(
        db, user_id=current_user.id, tenant_id=payload.tenant_id
    )
    return TokenPair(access_token=access, refresh_token=refresh)


@router.get("/me", response_model=MeResponse)
async def me(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    memberships = await auth_service.get_memberships_with_tenants(db, current_user.id)
    membership_out = [
        MembershipOut(
            id=m.id, role=m.role, tenant_id=m.tenant_id, user=UserOut.model_validate(current_user)
        )
        for m, _t in memberships
    ]
    return MeResponse(
        user=UserOut.model_validate(current_user),
        memberships=membership_out,
        current_tenant=None,
        current_role=None,
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.request_password_reset(db, email=payload.email)
    return MessageResponse(message="If that email exists, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.reset_password(db, token=payload.token, new_password=payload.new_password)
    return MessageResponse(message="Password reset successfully. You can now log in.")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await auth_service.change_password(
        db, user=current_user, current_password=payload.current_password, new_password=payload.new_password
    )
    return MessageResponse(message="Password changed successfully.")
