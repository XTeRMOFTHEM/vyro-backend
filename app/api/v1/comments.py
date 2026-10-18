"""VYRO — /api/v1/posts/{post_id}/comments + /api/v1/comments/{comment_id}."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, Db, OptionalUser, Page
from app.core.rate_limit import rate_limit
from app.schemas.comment import CommentActionOut, CommentCreateIn, CommentOut, CommentUpdateIn
from app.schemas.common import Ok, Page as PageModel
from app.services import comment_service

router = APIRouter(prefix="/posts/{post_id}/comments", tags=["comments"])
router_c = APIRouter(prefix="/comments", tags=["comments"])
_rl_write = Depends(rate_limit("30/60", scope="ip:path"))


@router.post("", response_model=CommentOut, status_code=201, dependencies=[_rl_write])
async def create_comment(post_id: uuid.UUID, body: CommentCreateIn, me: CurrentUser, db: Db):
    return await comment_service.create(db, me, post_id, body.content, body.parent_id)


@router.get("", response_model=PageModel)
async def list_comments(post_id: uuid.UUID, viewer: OptionalUser, db: Db, page: Page):
    return await comment_service.list_for_post(
        db, viewer.id if viewer else None, post_id, page.decoded_cursor, page.limit
    )


@router_c.get("/{comment_id}/replies", response_model=PageModel)
async def list_replies(comment_id: uuid.UUID, viewer: OptionalUser, db: Db, page: Page):
    return await comment_service.list_replies(
        db, viewer.id if viewer else None, comment_id, page.decoded_cursor, page.limit
    )


@router_c.patch("/{comment_id}", response_model=CommentOut)
async def edit_comment(comment_id: uuid.UUID, body: CommentUpdateIn, me: CurrentUser, db: Db):
    return await comment_service.edit(db, me, comment_id, body.content)


@router_c.delete("/{comment_id}", response_model=Ok)
async def delete_comment(comment_id: uuid.UUID, me: CurrentUser, db: Db):
    await comment_service.remove(db, me, comment_id)
    return Ok()


@router_c.post("/{comment_id}/like", response_model=CommentActionOut, dependencies=[_rl_write])
async def like_comment(comment_id: uuid.UUID, me: CurrentUser, db: Db):
    return await comment_service.like(db, me, comment_id)


@router_c.delete("/{comment_id}/like", response_model=CommentActionOut)
async def unlike_comment(comment_id: uuid.UUID, me: CurrentUser, db: Db):
    return await comment_service.unlike(db, me, comment_id)
