"""VYRO — /api/v1/feed + hashtags."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, Db, OptionalUser, Page
from app.schemas.common import Page as PageModel
from app.services import post_service

router = APIRouter(tags=["feed"])


@router.get("/feed/home", response_model=PageModel)
async def home_feed(me: CurrentUser, db: Db, page: Page):
    return await post_service.home_feed(db, me, page.decoded_cursor, page.limit)


@router.get("/feed/explore", response_model=PageModel)
async def explore(
    viewer: OptionalUser,
    db: Db,
    page: Page,
    mode: str = Query(default="latest", pattern="^(latest|trending)$"),
    pg: int = Query(default=1, ge=1, le=50),
):
    return await post_service.explore_feed(
        db, viewer.id if viewer else None, mode, page.decoded_cursor, pg, page.limit
    )


@router.get("/feed/saved", response_model=PageModel)
async def feed_saved(me: CurrentUser, db: Db, page: Page):
    return await post_service.saved_posts(db, me, page.decoded_cursor, page.limit)


@router.get("/feed/hashtag/{tag}", response_model=PageModel)
async def hashtag_feed(tag: str, viewer: OptionalUser, db: Db, page: Page):
    return await post_service.hashtag_posts(
        db, viewer.id if viewer else None, tag, page.decoded_cursor, page.limit
    )


@router.get("/hashtags/trending")
async def trending(db: Db, limit: int = Query(default=10, ge=1, le=30)):
    return {"items": await post_service.trending_hashtags(db, limit)}
