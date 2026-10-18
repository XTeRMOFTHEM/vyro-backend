"""VYRO — /api/v1/search."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import Db, OptionalUser
from app.services import search_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def search(
    db: Db,
    viewer: OptionalUser,
    q: str = Query(min_length=1, max_length=60),
    type: str = Query(default="all", pattern="^(all|users|posts|hashtags)$"),
    limit: int = Query(default=10, ge=1, le=30),
):
    return await search_service.search_all(
        db, q, type, viewer.id if viewer else None, limit
    )
