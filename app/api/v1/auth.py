"""VYRO — /api/v1/auth : register, login, refresh-rotation, verify, reset."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import CurrentUser, Db
from app.core.rate_limit import auth_rate_limit
from app.schemas.auth import (
    ChangePasswordIn, ForgotPasswordIn, LoginIn, LoginOut, LogoutIn, MessageOut,
    RefreshIn, RefreshOut, RegisterIn, RegisterOut, ResetPasswordIn,
    VerifyEmailIn,
)
from app.schemas.common import Ok
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
_auth_rl = Depends(auth_rate_limit())


@router.post("/register", response_model=RegisterOut, status_code=201, dependencies=[_auth_rl])
async def register(body: RegisterIn, request: Request, db: Db):
    ip = request.client.host if request.client else ""
    return await auth_service.register(
        db,
        email=body.email,
        username=body.username,
        password=body.password,
        display_name=body.display_name,
        ip=ip,
    )


@router.post("/login", response_model=LoginOut, dependencies=[_auth_rl])
async def login(body: LoginIn, request: Request, db: Db):
    ip = request.client.host if request.client else ""
    return await auth_service.login(
        db, email=body.email, password=body.password, device=body.device, ip=ip
    )


@router.post("/refresh", response_model=RefreshOut, dependencies=[_auth_rl])
async def refresh(body: RefreshIn, db: Db):
    return await auth_service.refresh(db, body.refresh_token)


@router.post("/logout", response_model=Ok)
async def logout(body: LogoutIn, db: Db):
    await auth_service.logout(db, body.refresh_token)
    return Ok()


@router.post("/logout-all", response_model=Ok)
async def logout_all(me: CurrentUser, db: Db):
    await auth_service.logout_all(db, me.id)
    return Ok()


@router.post("/verify-email", response_model=Ok, dependencies=[_auth_rl])
async def verify_email(body: VerifyEmailIn, db: Db):
    await auth_service.verify_email(db, body.token)
    return Ok()


@router.post("/resend-verification", response_model=MessageOut, dependencies=[_auth_rl])
async def resend_verification(me: CurrentUser, db: Db):
    await auth_service.resend_verification(db, me)
    return MessageOut(message="ایمیل تایید دوباره ارسال شد", dev_reset_token=None)


@router.post("/forgot-password", response_model=MessageOut, dependencies=[_auth_rl])
async def forgot_password(body: ForgotPasswordIn, db: Db):
    result = await auth_service.forgot_password(db, body.email)
    return MessageOut(**result)


@router.post("/reset-password", response_model=Ok, dependencies=[_auth_rl])
async def reset_password(body: ResetPasswordIn, db: Db):
    await auth_service.reset_password(db, body.token, body.new_password)
    return Ok()


@router.post("/change-password", response_model=Ok)
async def change_password(body: ChangePasswordIn, me: CurrentUser, db: Db):
    await auth_service.change_password(db, me, body.current_password, body.new_password)
    return Ok()
