"""VYRO — Admin service: platform stats, user management."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequest, Forbidden, UserNotFound
from app.models import (
    Comment, Conversation, Donation, Follow, LiveStream, Message, Notification,
    Post, Profile, User, Wallet,
)
from app.services import wallet_service
from app.services.user_service import author_mini


async def require_admin(user: User) -> None:
    if user.role != "admin":
        raise Forbidden("این عملیات فقط برای ادمین مجاز است")


async def platform_stats(db: AsyncSession) -> dict:
    async def count(model) -> int:
        return int(
            (await db.execute(select(func.count()).select_from(model))).scalar() or 0
        )

    stats = {
        "users": await count(User),
        "posts": int(
            (await db.execute(select(func.count()).select_from(Post).where(Post.is_deleted.is_(False)))).scalar() or 0
        ),
        "comments": await count(Comment),
        "messages": await count(Message),
        "follows": await count(Follow),
        "conversations": await count(Conversation),
        "donations": await count(Donation),
        "live_streams": await count(LiveStream),
    }
    zyra = (
        await db.execute(select(func.coalesce(func.sum(Wallet.balance), 0)))
    ).scalar()
    stats["zyra_in_circulation"] = int(zyra or 0)
    return stats


async def users_list(db: AsyncSession, q: str | None, cursor, limit: int) -> dict:
    from app.schemas.common import encode_cursor

    base = (
        select(Profile, User)
        .join(User, User.id == Profile.user_id)
        .order_by(Profile.created_at.desc(), Profile.user_id.desc())
    )
    if q:
        pattern = f"%{q.replace('%', r'\%').replace('_', r'\_')}%"
        base = base.where(
            (Profile.username.ilike(pattern, escape="\\"))
            | (User.email.ilike(pattern, escape="\\"))
        )
    if cursor:
        ts, id_ = cursor
        base = base.where((Profile.created_at, Profile.user_id) < (ts, id_))
    rows = (await db.execute(base.limit(limit + 1))).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = []
    for p, u in rows:
        items.append({**author_mini(p), "email": u.email, "role": u.role,
                      "is_active": u.is_active, "is_verified": u.is_verified,
                      "created_at": p.created_at})
    return {
        "items": items,
        "next_cursor": encode_cursor(rows[-1][0].created_at, rows[-1][0].user_id)
        if has_more and rows
        else None,
        "has_more": has_more,
    }


async def set_user_active(db: AsyncSession, user_id: uuid.UUID, active: bool) -> dict:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise UserNotFound()
    user.is_active = active
    await db.commit()
    return {"id": str(user.id), "username": user.profile.username, "is_active": user.is_active}


async def set_user_role(db: AsyncSession, user_id: uuid.UUID, role: str) -> dict:
    if role not in ("user", "moderator", "admin"):
        raise BadRequest("نقش نامعتبر است (user|moderator|admin)")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise UserNotFound()
    user.role = role
    await db.commit()
    return {"id": str(user.id), "username": user.profile.username, "role": user.role}
