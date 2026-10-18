"""VYRO — comment schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.post import AuthorMiniOut


class CommentCreateIn(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    parent_id: uuid.UUID | None = None


class CommentUpdateIn(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    post_id: uuid.UUID
    author: AuthorMiniOut
    parent_id: uuid.UUID | None = None
    content: str
    likes_count: int
    replies_count: int
    is_deleted: bool
    is_edited: bool = False
    edited_at: datetime | None = None
    created_at: datetime
    my_flags: dict | None = None


class CommentActionOut(BaseModel):
    ok: bool = True
    likes_count: int | None = None
    active: bool | None = None
