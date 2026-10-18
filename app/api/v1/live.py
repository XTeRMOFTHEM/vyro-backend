"""VYRO — /api/v1/live (BETA placeholder for future streaming integration)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, Db
from app.core.errors import BadRequest
from app.schemas.common import Ok
from app.services import live_service

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/streams")
async def list_streams(db: Db, status: str | None = Query(default=None), limit: int = Query(default=20, ge=1, le=50)):
    return {"items": await live_service.list_streams(db, status, limit), "beta": "Live streaming will ship in a future release"}


@router.post("/streams", status_code=201)
async def create_stream(body: dict, me: CurrentUser, db: Db):
    title = (body.get("title") or "").strip()
    if not title:
        raise BadRequest("عنوان لایو لازم است")
    return await live_service.create_stream(db, me, title, body.get("description", ""))


@router.get("/streams/{stream_id}")
async def get_stream(stream_id: uuid.UUID, me: CurrentUser, db: Db):
    return await live_service.get_stream(db, stream_id, me.id)


@router.post("/streams/{stream_id}/go-live")
async def go_live(stream_id: uuid.UUID, me: CurrentUser, db: Db):
    return await live_service.go_live(db, me, stream_id)


@router.post("/streams/{stream_id}/end", response_model=dict)
async def end_stream(stream_id: uuid.UUID, me: CurrentUser, db: Db):
    return await live_service.end_stream(db, me, stream_id)
