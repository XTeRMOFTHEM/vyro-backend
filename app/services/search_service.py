"""VYRO — Search: users / posts / hashtags (pg_trgm accelerated ILIKE)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Hashtag, Post, Profile, User
from app.services.post_service import _post_dict
from app.services.user_service import author_mini


def _escape_like(q: str) -> str:
    return q.replace("%", r"\%").replace("_", r"\_")


async def search_all(
    db: AsyncSession, query: str, kind: str, me_id, limit: int
) -> dict:
    query = query.strip().lstrip("@#")
    if len(query) < 2:
        return {"users": [], "posts": [], "hashtags": [], "users_total": 0, "posts_total": 0}

    pattern = f"%{_escape_like(query)}%"
    result: dict = {"users": [], "posts": [], "hashtags": []}

    if kind in ("all", "users"):
        rows = (
            await db.execute(
                select(Profile, User)
                .join(User, User.id == Profile.user_id)
                .where(
                    User.is_active.is_(True),
                    (Profile.username.ilike(pattern, escape="\\"))
                    | (Profile.display_name.ilike(pattern, escape="\\")),
                )
                .order_by(Profile.followers_count.desc())
                .limit(limit)
            )
        ).all()
        result["users"] = [author_mini(p) for p, _u in rows]
        total = (
            await db.execute(
                select(func.count())
                .select_from(Profile)
                .join(User, User.id == Profile.user_id)
                .where(
                    User.is_active.is_(True),
                    (Profile.username.ilike(pattern, escape="\\"))
                    | (Profile.display_name.ilike(pattern, escape="\\")),
                )
            )
        ).scalar()
        result["users_total"] = int(total or 0)

    if kind in ("all", "posts"):
        rows = (
            await db.execute(
                select(Post, Profile, User)
                .join(Profile, Profile.user_id == Post.author_id)
                .join(User, User.id == Profile.user_id)
                .where(Post.is_deleted.is_(False), Post.content.ilike(pattern, escape="\\"))
                .order_by(Post.likes_count.desc(), Post.created_at.desc())
                .limit(limit)
            )
        ).all()
        result["posts"] = [_post_dict(p, pr, u) for p, pr, u in rows]
        result["posts_total"] = len(result["posts"])

    if kind in ("all", "hashtags"):
        rows = (
            await db.execute(
                select(Hashtag)
                .where(Hashtag.name.ilike(f"{_escape_like(query)}%", escape="\\"))
                .order_by(Hashtag.posts_count.desc())
                .limit(limit)
            )
        ).scalars().all()
        result["hashtags"] = [{"name": h.name, "posts_count": h.posts_count} for h in rows]

    return result
