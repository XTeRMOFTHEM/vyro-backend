"""VYRO — Follow/Unfollow with atomic counters."""
from __future__ import annotations

import uuid

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.errors import BadRequest, UserNotFound
from app.models import Follow, Profile
from app.services import notification_service
from app.services.user_service import get_profile_by_username
from app.models.notification import TYPE_FOLLOW


async def follow(db: AsyncSession, me_id: uuid.UUID, username: str) -> dict:
    target = await get_profile_by_username(db, username)
    if target.user_id == me_id:
        raise BadRequest("نمی‌توانید خودتان را فالو کنید")

    result = await db.execute(
        pg_insert(Follow)
        .values(follower_id=me_id, following_id=target.user_id)
        .on_conflict_do_nothing()
        .returning(Follow.follower_id)
    )
    inserted = result.scalar_one_or_none() is not None

    if inserted:
        await db.execute(
            update(Profile)
            .where(Profile.user_id == me_id)
            .values(following_count=Profile.following_count + 1)
        )
        await db.execute(
            update(Profile)
            .where(Profile.user_id == target.user_id)
            .values(followers_count=Profile.followers_count + 1)
        )
        await notification_service.notify(
            db,
            recipient_id=target.user_id,
            type_=TYPE_FOLLOW,
            actor_id=me_id,
            ref_type="user",
            ref_id=me_id,
            data={"follow": True},
        )
        await db.commit()

    target_fresh = (
        await db.execute(select(Profile).where(Profile.id == target.id))
    ).scalar_one()
    return {"following": True, "followers_count": target_fresh.followers_count}


async def unfollow(db: AsyncSession, me_id: uuid.UUID, username: str) -> dict:
    target = await get_profile_by_username(db, username)
    if target.user_id == me_id:
        raise BadRequest("نمی‌توانید خودتان را آنفالو کنید")

    result = await db.execute(
        delete(Follow).where(Follow.follower_id == me_id, Follow.following_id == target.user_id)
    )
    removed = (result.rowcount or 0) > 0

    if removed:
        await db.execute(
            update(Profile)
            .where(Profile.user_id == me_id)
            .values(following_count=Profile.following_count - 1)
        )
        await db.execute(
            update(Profile)
            .where(Profile.user_id == target.user_id)
            .values(followers_count=Profile.followers_count - 1)
        )
        await db.commit()

    target_fresh = (
        await db.execute(select(Profile).where(Profile.id == target.id))
    ).scalar_one()
    return {"following": False, "followers_count": target_fresh.followers_count}


async def following_ids(db: AsyncSession, me_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await db.execute(select(Follow.following_id).where(Follow.follower_id == me_id))
    return {r[0] for r in rows.all()}
