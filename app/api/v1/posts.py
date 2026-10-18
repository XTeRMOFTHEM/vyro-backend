"""VYRO — /api/v1/posts : CRUD, like/save/repost/buff, social lists."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import CurrentUser, Db, OptionalUser, Page
from app.core.config import settings
from app.core.rate_limit import rate_limit
from app.schemas.common import Page as PageModel, Ok
from app.schemas.post import (
    BuffIn, BuffOut, PostActionOut, PostCreateIn, PostOut, PostUpdateIn, RepostIn,
)
from app.services import post_service

router = APIRouter(prefix="/posts", tags=["posts"])
_rl_write = Depends(rate_limit("30/60", scope="ip:path"))


@router.post("", response_model=PostOut, status_code=201, dependencies=[_rl_write])
async def create_post(
    me: CurrentUser,
    db: Db,
    content: Annotated[str, Form()] = "",
    image_urls: Annotated[list[str] | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
):
    return await post_service.create_post(
        db, me, content=content, image_urls=image_urls, files=files
    )


@router.get("/saved", response_model=PageModel)
async def saved(me: CurrentUser, db: Db, page: Page):
    return await post_service.saved_posts(db, me, page.decoded_cursor, page.limit)


@router.get("/{post_id}", response_model=PostOut)
async def get_post(post_id: uuid.UUID, viewer: OptionalUser, db: Db):
    return await post_service.post_dict_by_id(db, viewer.id if viewer else None, post_id)


@router.patch("/{post_id}", response_model=PostOut)
async def edit_post(post_id: uuid.UUID, body: PostUpdateIn, me: CurrentUser, db: Db):
    return await post_service.edit_post(db, me, post_id, body.content)


@router.delete("/{post_id}", response_model=Ok)
async def delete_post(post_id: uuid.UUID, me: CurrentUser, db: Db):
    await post_service.delete_post(db, me, post_id)
    return Ok()


@router.post("/{post_id}/like", response_model=PostActionOut, dependencies=[_rl_write])
async def like(post_id: uuid.UUID, me: CurrentUser, db: Db):
    return await post_service.like(db, me, post_id)


@router.delete("/{post_id}/like", response_model=PostActionOut)
async def unlike(post_id: uuid.UUID, me: CurrentUser, db: Db):
    return await post_service.unlike(db, me, post_id)


@router.post("/{post_id}/save", response_model=PostActionOut, dependencies=[_rl_write])
async def save(post_id: uuid.UUID, me: CurrentUser, db: Db):
    return await post_service.save(db, me, post_id)


@router.delete("/{post_id}/save", response_model=PostActionOut)
async def unsave(post_id: uuid.UUID, me: CurrentUser, db: Db):
    return await post_service.unsave(db, me, post_id)


@router.post("/{post_id}/repost", response_model=PostOut, dependencies=[_rl_write])
async def repost(post_id: uuid.UUID, body: RepostIn, me: CurrentUser, db: Db):
    return await post_service.repost(db, me, post_id, body.quote)


@router.delete("/{post_id}/repost", response_model=PostActionOut)
async def undo_repost(post_id: uuid.UUID, me: CurrentUser, db: Db):
    return await post_service.undo_repost(db, me, post_id)


@router.get("/{post_id}/likes", response_model=PageModel)
async def likes_list(post_id: uuid.UUID, db: Db, page: Page):
    return await post_service.post_likes(db, post_id, page.decoded_cursor, page.limit)


@router.get("/{post_id}/reposts", response_model=PageModel)
async def reposts_list(post_id: uuid.UUID, db: Db, page: Page):
    return await post_service.post_reposts(db, post_id, page.decoded_cursor, page.limit)


# ---------- buff (gift ZYRA on post) ----------

@router.post("/{post_id}/buff", response_model=dict, dependencies=[_rl_write])
async def buff_post(post_id: uuid.UUID, body: BuffIn, me: CurrentUser, db: Db):
    return await post_service.buff(db, me, post_id, body.amount, body.message)


@router.get("/{post_id}/buffs", response_model=PageModel)
async def buffs_list(post_id: uuid.UUID, db: Db, page: Page):
    return await post_service.post_buffs(db, post_id, page.decoded_cursor, page.limit)
