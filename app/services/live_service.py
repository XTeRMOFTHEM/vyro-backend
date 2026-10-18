"""VYRO — Live streaming service (BETA placeholder).

Core lifecycle exists so the module is integration-ready:
    create stream -> get stream_key -> (future: RTMP ingest) -> go live -> end.
Actual media transport (RTMP/SRT/WebRTC), viewer counting and live chat will
be added later; these stubs never block the rest of the platform.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequest, Forbidden, NotFound
from app.models import LiveStream, Profile
from app.models.base import utcnow
from app.models.live import new_stream_key, STATUS_ENDED, STATUS_LIVE, STATUS_SCHEDULED
from app.services.user_service import author_mini


def stream_dict(s: LiveStream, profile: Profile) -> dict:
    return {
        "id": str(s.id),
        "host": author_mini(profile),
        "title": s.title,
        "description": s.description,
        "status": s.status,
        "viewer_count": s.viewer_count,
        "peak_viewers": s.peak_viewers,
        "started_at": s.started_at,
        "ended_at": s.ended_at,
        "created_at": s.created_at,
        # stream_key only exposed to the host (via get_own_stream)
        "stream_key": None,
    }


async def create_stream(db: AsyncSession, me, title: str, description: str = "") -> dict:
    s = LiveStream(
        host_id=me.id,
        title=title.strip()[:120],
        description=description.strip()[:500],
        status=STATUS_SCHEDULED,
        stream_key=new_stream_key(),
    )
    db.add(s)
    await db.commit()
    data = stream_dict(s, me.profile)
    data["stream_key"] = s.stream_key  # host-only
    return data


async def get_stream(db: AsyncSession, stream_id: uuid.UUID, me_id=None) -> dict:
    s = (
        await db.execute(select(LiveStream).where(LiveStream.id == stream_id))
    ).scalar_one_or_none()
    if not s:
        raise NotFound("لایو یافت نشد", code="stream_not_found")
    p = (
        await db.execute(select(Profile).where(Profile.user_id == s.host_id))
    ).scalar_one()
    data = stream_dict(s, p)
    if me_id and s.host_id == me_id:
        data["stream_key"] = s.stream_key
    return data


async def list_streams(db: AsyncSession, status: str | None, limit: int) -> list[dict]:
    q = (
        select(LiveStream, Profile)
        .join(Profile, Profile.user_id == LiveStream.host_id)
        .order_by(LiveStream.created_at.desc())
        .limit(limit)
    )
    if status:
        q = q.where(LiveStream.status == status)
    rows = (await db.execute(q)).all()
    return [stream_dict(s, p) for s, p in rows]


async def go_live(db: AsyncSession, me, stream_id: uuid.UUID) -> dict:
    s = (
        await db.execute(select(LiveStream).where(LiveStream.id == stream_id))
    ).scalar_one_or_none()
    if not s:
        raise NotFound("لایو یافت نشد", code="stream_not_found")
    if s.host_id != me.id:
        raise Forbidden("فقط میزبان می‌تواند لایو را شروع کند")
    if s.status == STATUS_LIVE:
        raise BadRequest("لایو از قبل فعال است", code="already_live")
    s.status = STATUS_LIVE
    s.started_at = utcnow()
    await db.commit()
    data = stream_dict(s, me.profile)
    data["stream_key"] = s.stream_key
    return data


async def end_stream(db: AsyncSession, me, stream_id: uuid.UUID) -> dict:
    s = (
        await db.execute(select(LiveStream).where(LiveStream.id == stream_id))
    ).scalar_one_or_none()
    if not s:
        raise NotFound("لایو یافت نشد", code="stream_not_found")
    if s.host_id != me.id and me.role != "admin":
        raise Forbidden("فقط میزبان یا ادمین می‌تواند لایو را تمام کند")
    s.status = STATUS_ENDED
    s.ended_at = utcnow()
    await db.commit()
    data = stream_dict(s, me.profile)
    return data
