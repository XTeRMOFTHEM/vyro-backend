"""VYRO — Comment service (threaded, likes, soft delete)."""
from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.errors import BadRequest, CommentNotFound, Forbidden, PostNotFound
from app.models import Comment, CommentLike, Post, Profile, User
from app.models.base import utcnow
from app.services import notification_service, post_service
from app.services.user_service import author_mini
from app.models.notification import TYPE_COMMENT, TYPE_COMMENT_LIKE, TYPE_COMMENT_REPLY


def _comment_dict(c: Comment, profile: Profile) -> dict:
    return {
        "id": str(c.id),
        "post_id": str(c.post_id),
        "author": author_mini(profile),
        "parent_id": str(c.parent_id) if c.parent_id else None,
        "content": c.content,
        "likes_count": c.likes_count,
        "replies_count": c.replies_count,
        "is_deleted": c.is_deleted,
        "is_edited": c.edited_at is not None,
        "edited_at": c.edited_at,
        "created_at": c.created_at,
        "my_flags": None,
    }


async def _attach_liked(db: AsyncSession, me_id: uuid.UUID | None, items: list[dict]) -> None:
    if not me_id or not items:
        for it in items:
            it["my_flags"] = {"liked": False}
        return
    ids = [uuid.UUID(it["id"]) for it in items]
    liked = {
        r[0]
        for r in (
            await db.execute(
                select(CommentLike.comment_id).where(
                    CommentLike.user_id == me_id, CommentLike.comment_id.in_(ids)
                )
            )
        ).all()
    }
    for it in items:
        it["my_flags"] = {"liked": uuid.UUID(it["id"]) in liked}


async def create(
    db: AsyncSession, me: User, post_id: uuid.UUID, content: str, parent_id: uuid.UUID | None
) -> dict:
    post = await post_service.get_post_or_404(db, post_id)
    content = content.strip()
    if not content:
        raise BadRequest("متن کامنت خالی است")

    parent = None
    if parent_id:
        parent = (
            await db.execute(
                select(Comment).where(
                    Comment.id == parent_id,
                    Comment.post_id == post_id,
                    Comment.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if not parent:
            raise BadRequest("کامنت والد نامعتبر است", code="invalid_parent")

    c = Comment(post_id=post.id, author_id=me.id, parent_id=parent.id if parent else None, content=content)
    db.add(c)
    await db.flush()

    await db.execute(
        update(Post).where(Post.id == post.id).values(comments_count=Post.comments_count + 1)
    )
    if parent:
        await db.execute(
            update(Comment).where(Comment.id == parent.id).values(replies_count=Comment.replies_count + 1)
        )
        await notification_service.notify(
            db,
            recipient_id=parent.author_id,
            type_=TYPE_COMMENT_REPLY,
            actor_id=me.id,
            ref_type="comment",
            ref_id=c.id,
            data={
                "actor_username": me.profile.username,
                "post_id": str(post.id),
                "preview": content[:80],
            },
        )
    await notification_service.notify(
        db,
        recipient_id=post.author_id,
        type_=TYPE_COMMENT,
        actor_id=me.id,
        ref_type="post",
        ref_id=post.id,
        data={"actor_username": me.profile.username, "preview": content[:80]},
    )
    await db.commit()
    return _comment_dict(c, me.profile) | {"my_flags": {"liked": False}}


async def _get_or_404(db: AsyncSession, comment_id: uuid.UUID) -> Comment:
    c = (await db.execute(select(Comment).where(Comment.id == comment_id))).scalar_one_or_none()
    if not c:
        raise CommentNotFound()
    return c


async def edit(db: AsyncSession, me: User, comment_id: uuid.UUID, content: str) -> dict:
    c = await _get_or_404(db, comment_id)
    if c.author_id != me.id:
        raise Forbidden("فقط نویسنده می‌تواند کامنت را ویرایش کند")
    if c.is_deleted:
        raise BadRequest("کامنت حذف‌شده قابل ویرایش نیست")
    c.content = content.strip()
    c.edited_at = utcnow()
    await db.commit()
    return _comment_dict(c, me.profile)


async def remove(db: AsyncSession, me: User, comment_id: uuid.UUID) -> None:
    c = await _get_or_404(db, comment_id)
    if c.author_id != me.id and me.role != "admin":
        raise Forbidden("فقط نویسنده یا ادمین می‌تواند کامنت را حذف کند")
    if c.is_deleted:
        return
    c.is_deleted = True
    await db.execute(
        update(Post)
        .where(Post.id == c.post_id)
        .values(comments_count=func.greatest(Post.comments_count - 1, 0))
    )
    if c.parent_id:
        await db.execute(
            update(Comment)
            .where(Comment.id == c.parent_id)
            .values(replies_count=func.greatest(Comment.replies_count - 1, 0))
        )
    await db.commit()


async def like(db: AsyncSession, me: User, comment_id: uuid.UUID) -> dict:
    c = await _get_or_404(db, comment_id)
    res = await db.execute(
        pg_insert(CommentLike)
        .values(user_id=me.id, comment_id=c.id)
        .on_conflict_do_nothing()
        .returning(CommentLike.user_id)
    )
    inserted = res.scalar_one_or_none() is not None
    if inserted:
        await db.execute(
            update(Comment).where(Comment.id == c.id).values(likes_count=Comment.likes_count + 1)
        )
        await notification_service.notify(
            db,
            recipient_id=c.author_id,
            type_=TYPE_COMMENT_LIKE,
            actor_id=me.id,
            ref_type="comment",
            ref_id=c.id,
            data={"actor_username": me.profile.username, "preview": (c.content or "")[:80]},
        )
        await db.commit()
    fresh = (await db.execute(select(Comment.likes_count).where(Comment.id == c.id))).scalar_one()
    return {"ok": True, "likes_count": fresh, "active": True}


async def unlike(db: AsyncSession, me: User, comment_id: uuid.UUID) -> dict:
    c = await _get_or_404(db, comment_id)
    res = await db.execute(
        delete(CommentLike).where(CommentLike.user_id == me.id, CommentLike.comment_id == c.id)
    )
    removed = (res.rowcount or 0) > 0
    if removed:
        await db.execute(
            update(Comment)
            .where(Comment.id == c.id)
            .values(likes_count=func.greatest(Comment.likes_count - 1, 0))
        )
        await db.commit()
    fresh = (await db.execute(select(Comment.likes_count).where(Comment.id == c.id))).scalar_one()
    return {"ok": True, "likes_count": fresh, "active": False}


async def list_for_post(
    db: AsyncSession, me_id: uuid.UUID | None, post_id: uuid.UUID, cursor, limit: int
) -> dict:
    from app.schemas.common import encode_cursor

    await post_service.get_post_or_404(db, post_id)
    base = (
        select(Comment, Profile)
        .join(Profile, Profile.user_id == Comment.author_id)
        .where(Comment.post_id == post_id, Comment.parent_id.is_(None))
    )
    q = base.order_by(Comment.created_at.desc(), Comment.id.desc()).limit(limit + 1)
    if cursor:
        ts, id_ = cursor
        q = q.where((Comment.created_at, Comment.id) < (ts, id_))
    rows = (await db.execute(q)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [_comment_dict(c, p) for c, p in rows]
    await _attach_liked(db, me_id, items)
    return {
        "items": items,
        "next_cursor": encode_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None,
        "has_more": has_more,
    }


async def list_replies(
    db: AsyncSession, me_id: uuid.UUID | None, comment_id: uuid.UUID, cursor, limit: int
) -> dict:
    from app.schemas.common import encode_cursor

    parent = await _get_or_404(db, comment_id)
    base = (
        select(Comment, Profile)
        .join(Profile, Profile.user_id == Comment.author_id)
        .where(Comment.parent_id == parent.id)
    )
    q = base.order_by(Comment.created_at.asc(), Comment.id.asc()).limit(limit + 1)
    if cursor:
        ts, id_ = cursor
        q = q.where((Comment.created_at, Comment.id) > (ts, id_))  # asc keyset
    rows = (await db.execute(q)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [_comment_dict(c, p) for c, p in rows]
    await _attach_liked(db, me_id, items)
    next_cursor = (
        encode_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None
    )
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}
