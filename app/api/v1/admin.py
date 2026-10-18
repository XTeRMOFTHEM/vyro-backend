"""VYRO — /api/v1/admin : frames CRUD, grants, stats, user management."""
from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import AdminUser, Db, Page
from app.schemas.common import Ok, Page as PageModel
from app.schemas.frame import FrameCreateIn, FrameOut, FrameUpdateIn
from app.schemas.wallet import GrantIn
from app.services import admin_service, frame_service, user_service, wallet_service
from app.services.user_service import author_mini

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------- stats & users ----------

@router.get("/stats")
async def stats(admin: AdminUser, db: Db):
    return await admin_service.platform_stats(db)


@router.get("/users", response_model=PageModel)
async def users(admin: AdminUser, db: Db, page: Page, q: str | None = None):
    return await admin_service.users_list(db, q, page.decoded_cursor, page.limit)


@router.post("/users/{user_id}/activate", response_model=dict)
async def activate(user_id: uuid.UUID, admin: AdminUser, db: Db):
    return await admin_service.set_user_active(db, user_id, True)


@router.post("/users/{user_id}/deactivate", response_model=dict)
async def deactivate(user_id: uuid.UUID, admin: AdminUser, db: Db):
    return await admin_service.set_user_active(db, user_id, False)


@router.post("/users/{user_id}/role", response_model=dict)
async def set_role(user_id: uuid.UUID, body: dict, admin: AdminUser, db: Db):
    return await admin_service.set_user_role(db, user_id, body.get("role", "user"))


# ---------- ZYRA grants ----------

@router.post("/wallet/grant")
async def grant(body: GrantIn, admin: AdminUser, db: Db):
    from app.core.errors import BadRequest

    if not body.username and not body.user_id:
        raise BadRequest("username یا user_id لازم است")
    if body.user_id:
        from app.models import User
        from sqlalchemy import select

        user = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one_or_none()
        if not user:
            from app.core.errors import UserNotFound

            raise UserNotFound()
    else:
        profile = await user_service.get_profile_by_username(db, body.username)
        from app.models import User
        from sqlalchemy import select

        user = (await db.execute(select(User).where(User.id == profile.user_id))).scalar_one()
    wallet = await wallet_service.admin_grant(db, target_user_id=user.id, amount=body.amount, reason=body.reason)
    return {
        "ok": True,
        "user": {"id": str(user.id), "username": user.profile.username},
        "amount": body.amount,
        "new_balance": wallet.balance,
    }


# ---------- frames ----------

@router.post("/frames", response_model=FrameOut, status_code=201)
async def create_frame(body: FrameCreateIn, admin: AdminUser, db: Db):
    frame = await frame_service.admin_create_frame(db, body.model_dump())
    return user_service.frame_to_dict(frame)


@router.patch("/frames/{frame_id}", response_model=FrameOut)
async def update_frame(frame_id: uuid.UUID, body: FrameUpdateIn, admin: AdminUser, db: Db):
    frame = await frame_service.admin_update_frame(db, frame_id, body.model_dump(exclude_none=True))
    return user_service.frame_to_dict(frame)
