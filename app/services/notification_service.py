"""VYRO — Notification service (DB + realtime push over WebSocket)."""
from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, Profile, User
from app.models.notification import TYPE_COMMENT, TYPE_COMMENT_LIKE, TYPE_COMMENT_REPLY, TYPE_DONATION, TYPE_FOLLOW, TYPE_FRAME_PURCHASE, TYPE_LIKE, TYPE_REPOST, TYPE_BUFF  # noqa: F401
from app.models.base import utcnow


def _push(payload: dict) -> None:
    """Best-effort realtime push (never breaks the request)."""
    try:
        from app.ws.manager import manager

        import asyncio

        recipient = payload.get("recipient_id")
        if recipient:
            asyncio.get_running_loop().create_task(
                manager.send_to_user(uuid.UUID(str(recipient)), payload)
            )
    except Exception:
        pass


async def notify(
    db: AsyncSession,
    *,
    recipient_id: uuid.UUID,
    type_: str,
    actor_id: uuid.UUID | None = None,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
    data: dict | None = None,
) -> None:
    """Create a notification (same tx as caller) + realtime push."""
    if actor_id and actor_id == recipient_id:
        return  # no self-notifications
    notif = Notification(
        recipient_id=recipient_id,
        actor_id=actor_id,
        type=type_,
        ref_type=ref_type,
        ref_id=ref_id,
        data=data or {},
    )
    db.add(notif)
    await db.flush()
    actor_username = (data or {}).get("actor_username")
    _push({
        "type": "notification",
        "notification": {
            "id": str(notif.id),
            "type": type_,
            "ref_type": ref_type,
            "ref_id": str(ref_id) if ref_id else None,
            "data": data or {},
            "actor_username": actor_username,
            "is_read": False,
            "created_at": notif.created_at.isoformat() if notif.created_at else None,
        },
    })


async def list_notifications(
    db: AsyncSession, me_id: uuid.UUID, cursor: tuple | None, limit: int
) -> dict:
    from app.schemas.common import decode_cursor, encode_cursor

    q = (
        select(Notification, User, Profile)
        .join(User, User.id == Notification.actor_id, isouter=True)
        .join(Profile, Profile.user_id == User.id, isouter=True)
        .where(Notification.recipient_id == me_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        ts, id_ = cursor
        q = q.where(
            (Notification.created_at, Notification.id) < (ts, id_)
        )
    rows = (await db.execute(q)).all()

    has_more = len(rows) > limit
    rows = rows[:limit]
    items = []
    for notif, actor_user, actor_profile in rows:
        actor = None
        if actor_user and actor_profile:
            actor = {
                "id": str(actor_user.id),
                "username": actor_profile.username,
                "display_name": actor_profile.display_name,
                "avatar_url": actor_profile.avatar_url,
                "frame": None,
            }
        items.append({
            "id": str(notif.id),
            "type": notif.type,
            "actor": actor,
            "ref_type": notif.ref_type,
            "ref_id": str(notif.ref_id) if notif.ref_id else None,
            "data": notif.data or {},
            "is_read": notif.is_read,
            "created_at": notif.created_at,
        })
    next_cursor = (
        encode_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None
    )
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}


async def mark_read(db: AsyncSession, me_id: uuid.UUID, ids: list[uuid.UUID] | None) -> int:
    stmt = (
        update(Notification)
        .where(Notification.recipient_id == me_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    if ids:
        stmt = stmt.where(Notification.id.in_(ids))
    res = await db.execute(stmt)
    await db.commit()
    return res.rowcount or 0


async def unread_count(db: AsyncSession, me_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count(Notification.id)).where(
                Notification.recipient_id == me_id, Notification.is_read.is_(False)
            )
        )
    ).scalar() or 0
