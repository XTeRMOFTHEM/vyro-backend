"""VYRO — Auth service: register / login / refresh-rotation / verify / reset.

Security notes:
- bcrypt(12) password hashing
- opaque refresh tokens, SHA-256 hashed at rest, rotated on every refresh;
  reuse of a revoked token revokes the whole family (token-theft protection)
- no user enumeration on forgot-password
- rate limiting enforced at router level
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import BadRequest, Conflict, InvalidCredentials, Unauthorized
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import EmailToken, Profile, RefreshToken, User
from app.models.base import utcnow
from app.models.wallet import TX_SIGNUP_BONUS
from app.services import email_service, wallet_service


def _token_pair(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": "",
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


async def _issue_refresh(
    db: AsyncSession, user: User, device: str = "", ip: str = ""
) -> str:
    token = generate_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(token),
            device=device[:200],
            ip=ip[:64],
            expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    return token


async def _issue_pair(
    db: AsyncSession, user: User, device: str = "", ip: str = ""
) -> dict:
    payload = _token_pair(user)
    payload["refresh_token"] = await _issue_refresh(db, user, device, ip)
    return payload


async def _user_authed_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.profile.username,
        "display_name": user.profile.display_name,
        "role": user.role,
        "is_email_verified": user.is_verified,
    }


async def _email_exists(db: AsyncSession, email: str) -> bool:
    row = await db.execute(select(User.id).where(User.email == email.lower()))
    return row.scalar_one_or_none() is not None


async def _username_exists(db: AsyncSession, username: str) -> bool:
    row = await db.execute(select(Profile.id).where(Profile.username == username.lower()))
    return row.scalar_one_or_none() is not None


async def _create_email_token(
    db: AsyncSession, user: User, kind: str, hours: int
) -> str:
    token = generate_opaque_token()
    db.add(
        EmailToken(
            user_id=user.id,
            token_hash=hash_token(token),
            kind=kind,
            expires_at=utcnow() + timedelta(hours=hours),
        )
    )
    return token


async def register(
    db: AsyncSession, *, email: str, username: str, password: str,
    display_name: str | None, ip: str = "",
) -> dict:
    email = email.strip().lower()
    username = username.strip().lower()

    if await _email_exists(db, email):
        raise Conflict("این ایمیل قبلاً ثبت شده است")
    if await _username_exists(db, username):
        raise Conflict("این نام کاربری قبلاً گرفته شده است")

    user = User(
        email=email,
        password_hash=hash_password(password),
        is_verified=not settings.EMAIL_VERIFICATION_REQUIRED,
    )
    db.add(user)
    await db.flush()

    # link via relationship so user.profile is populated in-memory (no async lazy-load)
    profile = Profile(user=user, username=username, display_name=display_name or username)
    db.add(profile)
    await db.flush()
    # welcome gift: ZYRA signup bonus + ledger row
    wallet = await wallet_service.ensure_wallet(db, user.id)
    wallet.balance += settings.SIGNUP_BONUS_ZYRA
    wallet.total_earned += settings.SIGNUP_BONUS_ZYRA
    from app.services.wallet_service import _ledger

    _ledger(
        db, user_id=user.id, amount=settings.SIGNUP_BONUS_ZYRA,
        balance_after=wallet.balance, type_=TX_SIGNUP_BONUS, note="هدیه خوش‌آمدگویی VYRO",
    )

    dev_token = None
    if not user.is_verified:
        vtoken = await _create_email_token(
            db, user, EmailToken.KIND_VERIFY, settings.EMAIL_TOKEN_EXPIRE_HOURS
        )
        await db.commit()
        await email_service.send_email(email, "verify_email", username, vtoken)
        if settings.DEV_EXPOSE_EMAIL_TOKENS and not settings.SMTP_HOST:
            dev_token = vtoken
    else:
        await db.commit()

    pair = await _issue_pair(db, user, device="register", ip=ip)
    await db.commit()  # persist refresh token (issued after the earlier commit)
    return {
        **pair,
        "user": await _user_authed_dict(user),
        "dev_verification_token": dev_token,
    }


async def login(
    db: AsyncSession, *, email: str, password: str, device: str = "", ip: str = ""
) -> dict:
    email = email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise InvalidCredentials()
    if not user.is_active:
        raise Unauthorized("حساب کاربری غیرفعال است", code="account_disabled")

    user.last_login_at = utcnow()
    pair = await _issue_pair(db, user, device=device, ip=ip)
    await db.commit()
    return {**pair, "user": await _user_authed_dict(user)}


async def refresh(db: AsyncSession, refresh_token: str) -> dict:
    """Rotate refresh token; detect reuse of revoked tokens -> kill family."""
    rtoken = (
        await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
        )
    ).scalar_one_or_none()
    if not rtoken:
        raise Unauthorized("توکن refresh نامعتبر است", code="invalid_refresh_token")

    if rtoken.revoked_at is not None:
        # token reuse detected -> revoke all sessions of this user
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == rtoken.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        await db.commit()
        raise Unauthorized("نشست شما به‌دلیل تلاش استفاده مجدد از توکن، خاتمه یافت", code="refresh_reuse_detected")

    if rtoken.expires_at <= utcnow():
        raise Unauthorized("توکن refresh منقضی شده است", code="refresh_token_expired")

    user = (await db.execute(select(User).where(User.id == rtoken.user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise Unauthorized("کاربر نامعتبر است", code="invalid_refresh_token")

    rtoken.revoked_at = utcnow()  # rotate
    pair = await _issue_pair(db, user, device=rtoken.device, ip=rtoken.ip)
    await db.commit()
    return pair


async def logout(db: AsyncSession, refresh_token: str) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(refresh_token))
        .values(revoked_at=utcnow())
    )
    await db.commit()


async def logout_all(db: AsyncSession, me_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == me_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await db.commit()


async def verify_email(db: AsyncSession, token: str) -> None:
    et = (
        await db.execute(
            select(EmailToken).where(
                EmailToken.token_hash == hash_token(token),
                EmailToken.kind == EmailToken.KIND_VERIFY,
            )
        )
    ).scalar_one_or_none()
    if not et or et.used_at is not None or et.expires_at <= utcnow():
        raise BadRequest("توکن تایید نامعتبر یا منقضی شده است", code="invalid_verify_token")
    et.used_at = utcnow()
    await db.execute(update(User).where(User.id == et.user_id).values(is_verified=True))
    await db.commit()


async def resend_verification(db: AsyncSession, me: User) -> None:
    if me.is_verified:
        raise BadRequest("ایمیل شما قبلاً تایید شده است", code="already_verified")
    token = await _create_email_token(
        db, me, EmailToken.KIND_VERIFY, settings.EMAIL_TOKEN_EXPIRE_HOURS
    )
    await db.commit()
    await email_service.send_email(
        me.email, "verify_email", me.profile.username, token
    )


async def forgot_password(db: AsyncSession, email: str) -> dict:
    email = email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    dev_token = None
    if user:
        token = await _create_email_token(
            db, user, EmailToken.KIND_RESET, settings.RESET_TOKEN_EXPIRE_HOURS
        )
        await db.commit()
        await email_service.send_email(email, "reset_password", user.profile.username, token)
        if settings.DEV_EXPOSE_EMAIL_TOKENS and not settings.SMTP_HOST:
            dev_token = token
    # anti-enumeration: identical response either way
    return {"message": "اگر این ایمیل ثبت شده باشد، لینک بازیابی ارسال شد", "dev_reset_token": dev_token}


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    et = (
        await db.execute(
            select(EmailToken).where(
                EmailToken.token_hash == hash_token(token),
                EmailToken.kind == EmailToken.KIND_RESET,
            )
        )
    ).scalar_one_or_none()
    if not et or et.used_at is not None or et.expires_at <= utcnow():
        raise BadRequest("توکن بازیابی نامعتبر یا منقضی شده است", code="invalid_reset_token")
    et.used_at = utcnow()
    await db.execute(
        update(User)
        .where(User.id == et.user_id)
        .values(password_hash=hash_password(new_password))
    )
    # kill every session after password change
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == et.user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await db.commit()


async def change_password(db: AsyncSession, me: User, current: str, new_password: str) -> None:
    if not verify_password(current, me.password_hash):
        raise BadRequest("رمز عبور فعلی اشتباه است", code="wrong_current_password")
    if verify_password(new_password, me.password_hash):
        raise BadRequest("رمز جدید نباید با رمز فعلی یکسان باشد", code="same_password")
    me.password_hash = hash_password(new_password)
    await db.commit()
    # revoke other sessions (keep current device UX: we revoke all; client re-logins)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == me.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await db.commit()


async def user_from_access_token(db: AsyncSession, token: str) -> User:
    payload = decode_access_token(token)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as e:
        raise Unauthorized("توکن نامعتبر است", code="invalid_token") from e
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise Unauthorized("کاربر نامعتبر یا غیرفعال است", code="invalid_token")
    return user
