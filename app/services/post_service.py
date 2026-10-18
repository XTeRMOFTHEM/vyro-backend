"""VYRO — Post service: create/edit/delete, like/save/repost, feeds, buffs.

Performance notes:
- keyset (cursor) pagination everywhere — no OFFSET scans
- counters maintained with atomic UPDATE ... SET c = c ± 1
- viewer flags (liked/saved/reposted) computed with 3 batched IN-queries per page
- hashtags extracted unicode-aware (Persian supported)
"""
from __future__ import annotations

import uuid

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.cache import KEY_TRENDING_TAGS, cache
from app.core.config import settings
from app.core.errors import BadRequest, InsufficientBalance, NotFound, PostNotFound
from app.core.storage import storage
from app.models import (
    Follow, Hashtag, Like, Post, PostHashtag, Profile, Save, User,
)
from app.models.base import utcnow
from app.models.wallet import TX_BUFF_RECEIVED, TX_BUFF_SENT
from app.schemas.post import extract_hashtags
from app.services import notification_service, user_service, wallet_service
from app.services.user_service import author_mini
from app.models.notification import TYPE_BUFF, TYPE_COMMENT, TYPE_LIKE, TYPE_REPOST


# ---------------- builders ----------------

async def _profiles_for(db: AsyncSession, user_ids: list[uuid.UUID]) -> dict:
    if not user_ids:
        return {}
    rows = (
        await db.execute(
            select(Profile, User).join(User, User.id == Profile.user_id).where(
                Profile.user_id.in_(user_ids)
            )
        )
    ).all()
    return {p.user_id: (p, u) for p, u in rows}


async def _attach_flags(db: AsyncSession, me_id: uuid.UUID | None, items: list[dict]) -> None:
    if not me_id or not items:
        if items:
            for it in items:
                it["my_flags"] = None
        return
    ids = [uuid.UUID(it["id"]) for it in items]
    liked = {
        r[0] for r in (
            await db.execute(select(Like.post_id).where(Like.user_id == me_id, Like.post_id.in_(ids)))
        ).all()
    }
    saved = {
        r[0] for r in (
            await db.execute(select(Save.post_id).where(Save.user_id == me_id, Save.post_id.in_(ids)))
        ).all()
    }
    reposted = {
        r[0] for r in (
            await db.execute(
                select(Post.repost_of_id).where(
                    Post.author_id == me_id,
                    Post.repost_of_id.in_(ids),
                    Post.is_deleted.is_(False),
                )
            )
        ).all()
    }
    for it in items:
        pid = uuid.UUID(it["id"])
        it["my_flags"] = {
            "liked": pid in liked,
            "saved": pid in saved,
            "reposted": pid in reposted,
        }


def _post_dict(post: Post, profile: Profile, user: User) -> dict:
    return {
        "id": str(post.id),
        "author": author_mini(profile),
        "content": post.content,
        "images": post.images or [],
        "repost_of_id": str(post.repost_of_id) if post.repost_of_id else None,
        "repost_of": None,
        "likes_count": post.likes_count,
        "comments_count": post.comments_count,
        "reposts_count": post.reposts_count,
        "saves_count": post.saves_count,
        "buffs_count": post.buffs_count,
        "buffs_total_zyra": post.buffs_total_zyra,
        "is_edited": post.is_edited,
        "edited_at": post.edited_at,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
        "my_flags": None,
    }


async def _hydrate_reposts(db: AsyncSession, items: list[dict]) -> None:
    """Fill repost_of mini for repost rows."""
    orig_ids = [
        uuid.UUID(it["repost_of_id"]) for it in items
        if it.get("repost_of_id") and not it.get("repost_of")
    ]
    if not orig_ids:
        return
    rows = (
        await db.execute(
            select(Post, Profile)
            .join(Profile, Profile.user_id == Post.author_id)
            .where(Post.id.in_(orig_ids))
        )
    ).all()
    by_id = {p.id: (p, prof) for p, prof in rows}
    for it in items:
        oid = it.get("repost_of_id")
        if oid and oid in by_id:
            p, prof = by_id[oid]
            it["repost_of"] = {
                "id": str(p.id),
                "author": author_mini(prof),
                "content": (p.content or "")[:280],
                "images": (p.images or [])[:1],
                "created_at": p.created_at,
            }


# ---------------- hashtag helpers ----------------

async def _sync_hashtags(db: AsyncSession, post: Post, content: str, *, decrement: bool = False) -> None:
    tags = extract_hashtags(content)
    if decrement:
        old_ids = (
            await db.execute(select(PostHashtag.hashtag_id).where(PostHashtag.post_id == post.id))
        ).scalars().all()
        if old_ids:
            await db.execute(
                update(Hashtag)
                .where(Hashtag.id.in_(old_ids))
                .values(posts_count=func.greatest(Hashtag.posts_count - 1, 0))
            )
            await db.execute(delete(PostHashtag).where(PostHashtag.post_id == post.id))

    if not tags:
        return
    existing = (
        await db.execute(select(Hashtag).where(Hashtag.name.in_(tags)))
    ).scalars().all()
    have = {h.name: h for h in existing}
    for tag in tags:
        if tag not in have:
            h = Hashtag(name=tag, posts_count=0)
            db.add(h)
            await db.flush()
            have[tag] = h
    for h in have.values():
        if h.name in tags:
            await db.execute(
                update(Hashtag)
                .where(Hashtag.id == h.id)
                .values(posts_count=func.greatest(Hashtag.posts_count + (1 if not decrement else 0), 0))
            )
        await db.execute(
            pg_insert(PostHashtag)
            .values(post_id=post.id, hashtag_id=h.id)
            .on_conflict_do_nothing()
        )


# ---------------- CRUD ----------------

async def create_post(
    db: AsyncSession,
    me: User,
    *,
    content: str,
    image_urls: list[str] | None = None,
    files: list | None = None,
) -> dict:
    content = (content or "").strip()
    urls = list(image_urls or [])
    for f in (files or [])[: settings.MAX_IMAGES_PER_POST]:
        urls.append(await storage.save_image(f, "posts"))
    urls = urls[: settings.MAX_IMAGES_PER_POST]
    if not content and not urls:
        raise BadRequest("پست باید متن یا حداقل یک عکس داشته باشد")

    post = Post(author_id=me.id, content=content, images=urls)
    db.add(post)
    await db.flush()
    await _sync_hashtags(db, post, content)
    await db.execute(
        update(Profile).where(Profile.user_id == me.id).values(posts_count=Profile.posts_count + 1)
    )
    await db.commit()
    await cache.delete(KEY_TRENDING_TAGS)
    return {**_post_dict(post, me.profile, me), "my_flags": {"liked": False, "saved": False, "reposted": False}}


async def get_post_or_404(db: AsyncSession, post_id: uuid.UUID) -> Post:
    post = (
        await db.execute(
            select(Post).where(Post.id == post_id, Post.is_deleted.is_(False))
        )
    ).scalar_one_or_none()
    if not post:
        raise PostNotFound()
    return post


async def post_dict_by_id(db: AsyncSession, me_id: uuid.UUID | None, post_id: uuid.UUID) -> dict:
    post = await get_post_or_404(db, post_id)
    prof, user = (
        await db.execute(
            select(Profile, User)
            .join(User, User.id == Profile.user_id)
            .where(Profile.user_id == post.author_id)
        )
    ).one()
    data = _post_dict(post, prof, user)
    await _hydrate_reposts(db, [data])
    await _attach_flags(db, me_id, [data])
    return data


async def edit_post(db: AsyncSession, me: User, post_id: uuid.UUID, content: str) -> dict:
    post = await get_post_or_404(db, post_id)
    if post.author_id != me.id:
        from app.core.errors import Forbidden

        raise Forbidden("فقط نویسنده می‌تواند پست را ویرایش کند")
    content = content.strip()
    if not content and not (post.images or []):
        raise BadRequest("پست نمی‌تواند خالی شود")
    post.content = content
    post.is_edited = True
    post.edited_at = utcnow()
    await _sync_hashtags(db, post, content, decrement=True)
    await _sync_hashtags(db, post, content)
    await db.commit()
    await cache.delete(KEY_TRENDING_TAGS)
    return await post_dict_by_id(db, me.id, post.id)


async def delete_post(db: AsyncSession, me: User, post_id: uuid.UUID) -> None:
    post = await get_post_or_404(db, post_id)
    if post.author_id != me.id:
        from app.core.errors import Forbidden

        raise Forbidden("فقط نویسنده می‌تواند پست را حذف کند")
    post.is_deleted = True
    await _sync_hashtags(db, post, post.content or "", decrement=True)
    if not post.repost_of_id:  # original post only
        await db.execute(
            update(Profile)
            .where(Profile.user_id == me.id)
            .values(posts_count=func.greatest(Profile.posts_count - 1, 0))
        )
    else:
        await db.execute(
            update(Post)
            .where(Post.id == post.repost_of_id)
            .values(reposts_count=func.greatest(Post.reposts_count - 1, 0))
        )
    await db.commit()
    await cache.delete(KEY_TRENDING_TAGS)


# ---------------- like / save ----------------

async def like(db: AsyncSession, me: User, post_id: uuid.UUID) -> dict:
    post = await get_post_or_404(db, post_id)
    res = await db.execute(
        pg_insert(Like).values(user_id=me.id, post_id=post.id).on_conflict_do_nothing().returning(Like.user_id)
    )
    inserted = res.scalar_one_or_none() is not None
    if inserted:
        await db.execute(
            update(Post).where(Post.id == post.id).values(likes_count=Post.likes_count + 1)
        )
        await notification_service.notify(
            db,
            recipient_id=post.author_id,
            type_=TYPE_LIKE,
            actor_id=me.id,
            ref_type="post",
            ref_id=post.id,
            data={"actor_username": me.profile.username, "preview": (post.content or "")[:80]},
        )
        await db.commit()
    fresh = (await db.execute(select(Post.likes_count).where(Post.id == post.id))).scalar_one()
    return {"ok": True, "likes_count": fresh, "active": True}


async def unlike(db: AsyncSession, me: User, post_id: uuid.UUID) -> dict:
    post = await get_post_or_404(db, post_id)
    res = await db.execute(
        delete(Like).where(Like.user_id == me.id, Like.post_id == post.id)
    )
    removed = (res.rowcount or 0) > 0
    if removed:
        await db.execute(
            update(Post)
            .where(Post.id == post.id)
            .values(likes_count=func.greatest(Post.likes_count - 1, 0))
        )
        await db.commit()
    fresh = (await db.execute(select(Post.likes_count).where(Post.id == post.id))).scalar_one()
    return {"ok": True, "likes_count": fresh, "active": False}


async def save(db: AsyncSession, me: User, post_id: uuid.UUID) -> dict:
    post = await get_post_or_404(db, post_id)
    res = await db.execute(
        pg_insert(Save).values(user_id=me.id, post_id=post.id).on_conflict_do_nothing().returning(Save.user_id)
    )
    inserted = res.scalar_one_or_none() is not None
    if inserted:
        await db.execute(
            update(Post).where(Post.id == post.id).values(saves_count=Post.saves_count + 1)
        )
        await db.commit()
    fresh = (await db.execute(select(Post.saves_count).where(Post.id == post.id))).scalar_one()
    return {"ok": True, "saves_count": fresh, "active": True}


async def unsave(db: AsyncSession, me: User, post_id: uuid.UUID) -> dict:
    post = await get_post_or_404(db, post_id)
    res = await db.execute(
        delete(Save).where(Save.user_id == me.id, Save.post_id == post.id)
    )
    removed = (res.rowcount or 0) > 0
    if removed:
        await db.execute(
            update(Post)
            .where(Post.id == post.id)
            .values(saves_count=func.greatest(Post.saves_count - 1, 0))
        )
        await db.commit()
    fresh = (await db.execute(select(Post.saves_count).where(Post.id == post.id))).scalar_one()
    return {"ok": True, "saves_count": fresh, "active": False}


# ---------------- repost ----------------

async def repost(db: AsyncSession, me: User, post_id: uuid.UUID, quote: str = "") -> dict:
    original = await get_post_or_404(db, post_id)
    target_id = original.repost_of_id or original.id  # repost-of-repost resolves to original

    already = (
        await db.execute(
            select(Post.id).where(
                Post.author_id == me.id,
                Post.repost_of_id == target_id,
                Post.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if already:
        raise BadRequest("شما قبلاً این پست را ریپست کرده‌اید", code="already_reposted")

    row = Post(
        author_id=me.id,
        content=(quote or "").strip(),
        images=[],
        repost_of_id=target_id,
    )
    db.add(row)
    await db.flush()
    if quote.strip():
        await _sync_hashtags(db, row, quote)
    await db.execute(
        update(Post).where(Post.id == target_id).values(reposts_count=Post.reposts_count + 1)
    )
    await notification_service.notify(
        db,
        recipient_id=original.author_id,
        type_=TYPE_REPOST,
        actor_id=me.id,
        ref_type="post",
        ref_id=target_id,
        data={"actor_username": me.profile.username},
    )
    await db.commit()
    return await post_dict_by_id(db, me.id, row.id)


async def undo_repost(db: AsyncSession, me: User, post_id: uuid.UUID) -> dict:
    original = await get_post_or_404(db, post_id)
    target_id = original.repost_of_id or original.id
    res = await db.execute(
        update(Post)
        .where(
            Post.author_id == me.id,
            Post.repost_of_id == target_id,
            Post.is_deleted.is_(False),
        )
        .values(is_deleted=True)
    )
    removed = (res.rowcount or 0) > 0
    if removed:
        await db.execute(
            update(Post)
            .where(Post.id == target_id)
            .values(reposts_count=func.greatest(Post.reposts_count - 1, 0))
        )
        await db.commit()
    fresh = (await db.execute(select(Post.reposts_count).where(Post.id == target_id))).scalar_one()
    return {"ok": True, "reposts_count": fresh, "active": False}


# ---------------- buff (gift ZYRA on a post) ----------------

async def buff(db: AsyncSession, me: User, post_id: uuid.UUID, amount: int, message: str) -> dict:
    if not (settings.BUFF_MIN <= amount <= settings.BUFF_MAX):
        raise BadRequest(
            f"مقدار buff باید بین {settings.BUFF_MIN} تا {settings.BUFF_MAX} باشد",
            code="buff_amount_out_of_range",
        )
    post = await get_post_or_404(db, post_id)
    from app.models import Buff

    sender_w, _ = await wallet_service.transfer(
        db,
        sender_id=me.id,
        recipient_id=post.author_id,
        amount=amount,
        sent_type=TX_BUFF_SENT,
        received_type=TX_BUFF_RECEIVED,
        ref_type="post",
        ref_id=post.id,
        note=message or "Buff روی پست",
        commit=False,
    )
    buff_row = Buff(sender_id=me.id, post_id=post.id, amount=amount, message=message or "")
    db.add(buff_row)
    await db.flush()
    await db.execute(
        update(Post)
        .where(Post.id == post.id)
        .values(
            buffs_total_zyra=Post.buffs_total_zyra + amount,
            buffs_count=Post.buffs_count + 1,
        )
    )
    await notification_service.notify(
        db,
        recipient_id=post.author_id,
        type_=TYPE_BUFF,
        actor_id=me.id,
        ref_type="post",
        ref_id=post.id,
        data={
            "actor_username": me.profile.username,
            "amount": amount,
            "message": message,
            "preview": (post.content or "")[:80],
        },
    )
    await db.commit()
    return {
        "ok": True,
        "buff_id": str(buff_row.id),
        "amount": amount,
        "post_buffs_total_zyra": post.buffs_total_zyra + amount,
        "sender_balance": sender_w.balance,
    }


async def post_buffs(db: AsyncSession, post_id: uuid.UUID, cursor, limit: int) -> dict:
    from app.models import Buff
    from app.schemas.common import encode_cursor

    await get_post_or_404(db, post_id)
    q = (
        select(Buff, Profile)
        .join(Profile, Profile.user_id == Buff.sender_id)
        .where(Buff.post_id == post_id)
        .order_by(Buff.created_at.desc(), Buff.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        ts, id_ = cursor
        q = q.where((Buff.created_at, Buff.id) < (ts, id_))
    rows = (await db.execute(q)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [
        {
            "id": str(b.id),
            "amount": b.amount,
            "message": b.message,
            "created_at": b.created_at,
            "sender": author_mini(p),
        }
        for b, p in rows
    ]
    return {
        "items": items,
        "next_cursor": encode_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None,
        "has_more": has_more,
    }


# ---------------- lists & feeds ----------------

async def _list_query(
    db: AsyncSession,
    base,
    cursor: tuple | None,
    limit: int,
    ts_col,
    id_col,
) -> tuple[list, bool]:
    q = base.order_by(ts_col.desc(), id_col.desc()).limit(limit + 1)
    if cursor:
        ts, id_ = cursor
        q = q.where((ts_col, id_col) < (ts, id_))
    rows = (await db.execute(q)).all()
    has_more = len(rows) > limit
    return rows[:limit], has_more


async def user_posts(
    db: AsyncSession, me_id: uuid.UUID | None, username: str, cursor, limit: int
) -> dict:
    from app.schemas.common import encode_cursor

    profile = await user_service.get_profile_by_username(db, username)
    base = (
        select(Post, Profile, User)
        .join(Profile, Profile.user_id == Post.author_id)
        .join(User, User.id == Profile.user_id)
        .where(Post.author_id == profile.user_id, Post.is_deleted.is_(False))
    )
    rows, has_more = await _list_query(db, base, cursor, limit, Post.created_at, Post.id)
    items = [_post_dict(p, pr, u) for p, pr, u in rows]
    await _hydrate_reposts(db, items)
    await _attach_flags(db, me_id, items)
    return {
        "items": items,
        "next_cursor": encode_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None,
        "has_more": has_more,
    }


async def home_feed(
    db: AsyncSession, me: User, cursor, limit: int
) -> dict:
    """Posts of people I follow + my own (timeline v1: SQL join; fan-out later)."""
    from app.schemas.common import encode_cursor

    base = (
        select(Post, Profile, User)
        .join(Profile, Profile.user_id == Post.author_id)
        .join(User, User.id == Profile.user_id)
        .where(
            Post.is_deleted.is_(False),
            or_(
                Post.author_id.in_(select(Follow.following_id).where(Follow.follower_id == me.id)),
                Post.author_id == me.id,
            ),
        )
    )
    rows, has_more = await _list_query(db, base, cursor, limit, Post.created_at, Post.id)
    items = [_post_dict(p, pr, u) for p, pr, u in rows]
    await _hydrate_reposts(db, items)
    await _attach_flags(db, me.id, items)
    return {
        "items": items,
        "next_cursor": encode_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None,
        "has_more": has_more,
    }


async def explore_feed(
    db: AsyncSession, me_id: uuid.UUID | None, mode: str, cursor, page: int, limit: int
) -> dict:
    from app.schemas.common import encode_cursor

    base = (
        select(Post, Profile, User)
        .join(Profile, Profile.user_id == Post.author_id)
        .join(User, User.id == Profile.user_id)
        .where(Post.is_deleted.is_(False))
    )
    if mode == "trending":
        score = (
            Post.likes_count * 3
            + Post.comments_count * 4
            + Post.reposts_count * 2
            + Post.buffs_count * 5
            + Post.saves_count * 2
        )
        base = base.where(Post.created_at > utcnow() - func.make_interval(0, 0, 0, 30)).order_by(
            score.desc(), Post.created_at.desc(), Post.id.desc()
        )
        page = max(page, 1)
        base = base.offset((page - 1) * limit)
        rows = (await db.execute(base.limit(limit))).all()
        items = [_post_dict(p, pr, u) for p, pr, u in rows]
        await _hydrate_reposts(db, items)
        await _attach_flags(db, me_id, items)
        return {
            "items": items,
            "next_cursor": None,
            "has_more": len(rows) == limit and page < 50,
            "page": page,
        }
    # latest (keyset)
    rows, has_more = await _list_query(db, base, cursor, limit, Post.created_at, Post.id)
    items = [_post_dict(p, pr, u) for p, pr, u in rows]
    await _hydrate_reposts(db, items)
    await _attach_flags(db, me_id, items)
    return {
        "items": items,
        "next_cursor": encode_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None,
        "has_more": has_more,
        "page": 1,
    }


async def hashtag_posts(
    db: AsyncSession, me_id: uuid.UUID | None, tag: str, cursor, limit: int
) -> dict:
    from app.schemas.common import encode_cursor

    tag = tag.strip().lstrip("#").lower()
    tag_row = (
        await db.execute(select(Hashtag).where(Hashtag.name == tag))
    ).scalar_one_or_none()
    if not tag_row:
        return {"hashtag": {"name": tag, "posts_count": 0}, "items": [], "next_cursor": None, "has_more": False}

    base = (
        select(Post, Profile, User)
        .join(PostHashtag, PostHashtag.post_id == Post.id)
        .join(Profile, Profile.user_id == Post.author_id)
        .join(User, User.id == Profile.user_id)
        .where(PostHashtag.hashtag_id == tag_row.id, Post.is_deleted.is_(False))
    )
    rows, has_more = await _list_query(db, base, cursor, limit, Post.created_at, Post.id)
    items = [_post_dict(p, pr, u) for p, pr, u in rows]
    await _hydrate_reposts(db, items)
    await _attach_flags(db, me_id, items)
    return {
        "hashtag": {"name": tag_row.name, "posts_count": tag_row.posts_count},
        "items": items,
        "next_cursor": encode_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None,
        "has_more": has_more,
    }


async def saved_posts(db: AsyncSession, me: User, cursor, limit: int) -> dict:
    from app.schemas.common import encode_cursor

    from app.models import Save

    base = (
        select(Post, Profile, User, Save)
        .join(Save, Save.post_id == Post.id)
        .join(Profile, Profile.user_id == Post.author_id)
        .join(User, User.id == Profile.user_id)
        .where(Save.user_id == me.id, Post.is_deleted.is_(False))
    )
    rows, has_more = await _list_query(db, base, cursor, limit, Save.created_at, Post.id)
    items = [_post_dict(p, pr, u) for p, pr, u, _s in rows]
    await _hydrate_reposts(db, items)
    await _attach_flags(db, me.id, items)
    return {
        "items": items,
        "next_cursor": encode_cursor(rows[-1][3].created_at, rows[-1][0].id) if has_more and rows else None,
        "has_more": has_more,
    }


async def post_likes(db: AsyncSession, post_id: uuid.UUID, cursor, limit: int) -> dict:
    from app.schemas.common import encode_cursor

    await get_post_or_404(db, post_id)
    base = (
        select(Like, Profile)
        .join(Profile, Profile.user_id == Like.user_id)
        .where(Like.post_id == post_id)
    )
    rows, has_more = await _list_query(db, base, cursor, limit, Like.created_at, Like.user_id)
    return {
        "items": [author_mini(p) for _l, p in rows],
        "next_cursor": encode_cursor(rows[-1][0].created_at, rows[-1][0].user_id) if has_more and rows else None,
        "has_more": has_more,
    }


async def post_reposts(db: AsyncSession, post_id: uuid.UUID, cursor, limit: int) -> dict:
    from app.schemas.common import encode_cursor

    await get_post_or_404(db, post_id)
    base = (
        select(Post, Profile)
        .join(Profile, Profile.user_id == Post.author_id)
        .where(Post.repost_of_id == post_id, Post.is_deleted.is_(False))
    )
    rows, has_more = await _list_query(db, base, cursor, limit, Post.created_at, Post.id)
    return {
        "items": [author_mini(p) for _p, p in rows],
        "next_cursor": encode_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None,
        "has_more": has_more,
    }


async def trending_hashtags(db: AsyncSession, limit: int = 10) -> list[dict]:
    async def _compute():
        since = utcnow() - func.make_interval(0, 0, 0, 7)
        q = (
            select(Hashtag.id, Hashtag.name, func.count(PostHashtag.post_id).label("cnt"))
            .join(PostHashtag, PostHashtag.hashtag_id == Hashtag.id)
            .join(Post, Post.id == PostHashtag.post_id)
            .where(Post.is_deleted.is_(False), Post.created_at > since)
            .group_by(Hashtag.id)
            .order_by(func.count(PostHashtag.post_id).desc())
            .limit(limit)
        )
        rows = (await db.execute(q)).all()
        return [{"name": r.name, "posts_count": r.cnt} for r in rows]

    return await cache.get_or_set(KEY_TRENDING_TAGS, _compute, ttl=120) or []
