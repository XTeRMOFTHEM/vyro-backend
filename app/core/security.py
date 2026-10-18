"""VYRO — Security primitives: password hashing (bcrypt), JWT access tokens,
opaque refresh tokens (hashed at rest), single-use email tokens."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import AppError, Unauthorized


# ---------------- Passwords ----------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------- JWT access token ----------------

def create_access_token(user_id: uuid.UUID | str, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
        "jti": secrets.token_hex(8),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError as e:
        raise Unauthorized("توکن منقضی شده است", code="token_expired") from e
    except jwt.InvalidTokenError as e:
        raise Unauthorized("توکن نامعتبر است", code="invalid_token") from e
    if payload.get("type") != "access":
        raise Unauthorized("نوع توکن نامعتبر است", code="invalid_token")
    return payload


# ---------------- Opaque tokens (refresh / email) ----------------

def generate_opaque_token() -> str:
    """High-entropy URL-safe token; only its SHA-256 hash is stored."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# ---------------- misc ----------------

def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
