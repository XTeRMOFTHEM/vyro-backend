"""VYRO — /api/v1/notifications."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Body

from app.api.deps import CurrentUser, Db, Page
from app.schemas.common import Ok, Page as PageModel
from app.schemas.notification import NotificationOut, ReadAllOut, UnreadCountOut
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=PageModel)
async def list_notifications(me: CurrentUser, db: Db, page: Page):
    return await notification_service.list_notifications(
        db, me.id, page.decoded_cursor, page.limit
    )


@router.get("/unread-count", response_model=UnreadCountOut)
async def unread(me: CurrentUser, db: Db):
    return {"unread_count": await notification_service.unread_count(db, me.id)}


@router.post("/read", response_model=ReadAllOut)
async def mark_read(
    me: CurrentUser,
    db: Db,
    ids: list[uuid.UUID] | None = Body(default=None),
):
    marked = await notification_service.mark_read(db, me.id, ids)
    return {"ok": True, "marked": marked}
