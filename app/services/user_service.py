"""VYRO — User/Profile service."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import KEY_PROFILE_PREFIX, cache
from app.core.config import settings
from app.core.errors import BadRequest, Conflict, UserNotFound
from app.core.storage import storage
from app.models import Follow, Profile, User
from app.models.base import utcnow


async def get_user_with_profile(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise UserNotFound()
    return user


async def get_profile_by_username(db: AsyncSession, username: str) -> Profile:
    profile = (
        await db.execute(
            select(Profile).where(Profile.username == username.strip().lower())
        )
    ).scalar_one_or_none()
    if not profile:
        raise UserNotFound()
    return profile


def frame_to_dict(frame) -> dict | None:
    if not frame:
        return None
    return {
        "id": str(frame.id),
        "slug": frame.slug,
        "name": frame.name,
        "description": frame.description or "",
        "rarity": frame.rarity,
        "price_zyra": frame.price_zyra,
        "is_active": frame.is_active,
        "is_limited": frame.is_limited,
        "animation_type": frame.animation_type,
        "asset_url": frame.asset_url,
        "preview_url": frame.preview_url,
        "config": frame.config or {},
        "created_at": frame.created_at,
    }


def author_mini(profile: Profile, frame=None) -> dict:
    return {
        "id": str(profile.user_id),
        "username": profile.username,
        "display_name": profile.display_name,
        "avatar_url": profile.avatar_url,
        "frame": frame_to_dict(frame if frame is not None else profile.frame),
    }


async def is_following(db: AsyncSession, me_id: uuid.UUID, target_id: uuid.UUID) -> bool:
    if me_id == target_id:
        return False
    row = (
        await db.execute(
            select(Follow.follower_id).where(
                Follow.follower_id == me_id, Follow.following_id == target_id
            )
        )
    ).first()
    return row is not None


async def profile_public_dict(
    db: AsyncSession, profile: Profile, viewer_id: uuid.UUID | None
) -> dict:
    user = (await db.execute(select(User).where(User.id == profile.user_id))).scalar_one()
    data = {
        "id": str(profile.user_id),
        "username": profile.username,
        "display_name": profile.display_name,
        "bio": profile.bio or "",
        "avatar_url": profile.avatar_url,
        "banner_url": profile.banner_url,
        "frame": frame_to_dict(profile.frame),
        "followers_count": profile.followers_count,
        "following_count": profile.following_count,
        "posts_count": profile.posts_count,
        "is_verified": user.is_verified,
        "created_at": profile.created_at,
        "is_following": None,
        "is_self": None,
    }
    if viewer_id:
        data["is_self"] = viewer_id == profile.user_id
        if not data["is_self"]:
            data["is_following"] = await is_following(db, viewer_id, profile.user_id)
    return data


async def me_dict(db: AsyncSession, user: User) -> dict:
    from app.services.wallet_service import wallet_info

    wallet = await wallet_info(db, user.id)
    profile = user.profile
    return {
        "id": str(user.id),
        "username": profile.username,
        "display_name": profile.display_name,
        "bio": profile.bio or "",
        "email": user.email,
        "role": user.role,
        "is_email_verified": user.is_verified,
        "avatar_url": profile.avatar_url,
        "banner_url": profile.banner_url,
        "frame": frame_to_dict(profile.frame),
        "followers_count": profile.followers_count,
        "following_count": profile.following_count,
        "posts_count": profile.posts_count,
        "created_at": profile.created_at,
        "wallet": wallet,
    }


async def update_profile(
    db: AsyncSession, me: User, display_name: str | None, bio: str | None
) -> dict:
    profile = me.profile
    if display_name is not None and display_name != profile.display_name:
        profile.display_name = display_name
    if bio is not None:
        profile.bio = bio
    await db.commit()
    await cache.delete(f"{KEY_PROFILE_PREFIX}{profile.username}")
    return await me_dict(db, me)


async def change_username(db: AsyncSession, me: User, new_username: str) -> dict:
    new_username = new_username.strip().lower()
    profile = me.profile
    if new_username == profile.username:
        raise BadRequest("نام کاربری جدید باید با قبلی متفاوت باشد")

    cooldown = timedelta(days=settings.USERNAME_CHANGE_COOLDOWN_DAYS)
    if profile.username_changed_at and (utcnow() - profile.username_changed_at) < cooldown:
        remaining = cooldown - (utcnow() - profile.username_changed_at)
        days = remaining.days + (1 if remaining.seconds else 0)
        raise BadRequest(
            f"تغییر نام کاربری هر {settings.USERNAME_CHANGE_COOLDOWN_DAYS} روز یک‌بار مجاز است "
            f"({days} روز دیگر)",
            code="username_cooldown",
        )

    exists = (
        await db.execute(select(Profile.id).where(Profile.username == new_username))
    ).scalar_one_or_none()
    if exists:
        raise Conflict("این نام کاربری قبلاً گرفته شده است")

    old = profile.username
    profile.username = new_username
    profile.username_changed_at = utcnow()
    await db.commit()
    await cache.delete(f"{KEY_PROFILE_PREFIX}{old}")
    await cache.delete(f"{KEY_PROFILE_PREFIX}{new_username}")
    return await me_dict(db, me)


async def set_avatar(db: AsyncSession, me: User, url: str) -> dict:
    old = me.profile.avatar_url
    me.profile.avatar_url = url
    await db.commit()
    await cache.delete(f"{KEY_PROFILE_PREFIX}{me.profile.username}")
    _safe_delete(old)
    return await me_dict(db, me)


async def set_banner(db: AsyncSession, me: User, url: str) -> dict:
    old = me.profile.banner_url
    me.profile.banner_url = url
    await db.commit()
    await cache.delete(f"{KEY_PROFILE_PREFIX}{me.profile.username}")
    _safe_delete(old)
    return await me_dict(db, me)


def _safe_delete(url: str | None) -> None:
    if not url or not url.startswith("/media/uploads/"):
        return
    try:
        path = storage.root / url.removeprefix("/media/")
        if path.exists():
            path.unlink()
    except OSError:
        pass


async def followers_list(
    db: AsyncSession, target_profile: Profile, cursor: tuple | None, limit: int
) -> dict:
    """Users who follow target (keyset by follow.created_at)."""
    from app.schemas.common import encode_cursor

    from app.models.follow import Follow

    q = (
        select(Follow, Profile, User)
        .join(Profile, Profile.user_id == Follow.follower_id)
        .join(User, User.id == Follow.follower_id)
        .where(Follow.following_id == target_profile.user_id, User.is_active.is_(True))
        .order_by(Follow.created_at.desc(), Follow.follower_id.desc())
        .limit(limit + 1)
    )
    if cursor:
        ts, id_ = cursor
        q = q.where((Follow.created_at, Follow.follower_id) < (ts, id_))
    rows = (await db.execute(q)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [author_mini(p) for _f, p, _u in rows]
    return {
        "items": items,
        "next_cursor": encode_cursor(rows[-1][0].created_at, rows[-1][0].follower_id)
        if has_more and rows
        else None,
        "has_more": has_more,
    }


async def following_list(
    db: AsyncSession, target_profile: Profile, cursor: tuple | None, limit: int
) -> dict:
    from app.schemas.common import encode_cursor

    from app.models.follow import Follow

    q = (
        select(Follow, Profile, User)
        .join(Profile, Profile.user_id == Follow.following_id)
        .join(User, User.id == Follow.following_id)
        .where(Follow.follower_id == target_profile.user_id, User.is_active.is_(True))
        .order_by(Follow.created_at.desc(), Follow.following_id.desc())
        .limit(limit + 1)
    )
    if cursor:
        ts, id_ = cursor
        q = q.where((Follow.created_at, Follow.following_id) < (ts, id_))
    rows = (await db.execute(q)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [author_mini(p) for _f, p, _u in rows]
    return {
        "items": items,
        "next_cursor": encode_cursor(rows[-1][0].created_at, rows[-1][0].following_id)
        if has_more and rows
        else None,
        "has_more": has_more,
    }
