"""VYRO — shared API dependencies: auth, admin, pagination."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import Forbidden, Unauthorized
from app.models import User
from app.services import auth_service

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise Unauthorized("هدر Authorization با توکن Bearer لازم است")
    return await auth_service.user_from_access_token(db, credentials.credentials)


async def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    if not credentials or credentials.scheme.lower() != "bearer":
        return None
    try:
        return await auth_service.user_from_access_token(db, credentials.credentials)
    except Unauthorized:
        return None


async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "admin":
        raise Forbidden("این عملیات فقط برای ادمین مجاز است")
    return user


# ---------- pagination ----------
class Pagination:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
        cursor: Annotated[str | None, Query()] = None,
    ):
        self.limit = limit
        self.cursor = cursor

    @property
    def decoded_cursor(self):
        from app.schemas.common import decode_cursor

        return decode_cursor(self.cursor) if self.cursor else None


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
AdminUser = Annotated[User, Depends(require_admin)]
Db = Annotated[AsyncSession, Depends(get_db)]
Page = Annotated[Pagination, Depends(Pagination)]
