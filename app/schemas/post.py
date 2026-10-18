"""VYRO — post schemas."""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

HASHTAG_RE = re.compile(r"#([\w\u0600-\u06FF]{2,30})", re.UNICODE)


def extract_hashtags(text: str) -> list[str]:
    """Unique, lowercased hashtags (unicode-aware: Persian supported)."""
    seen: list[str] = []
    for m in HASHTAG_RE.finditer(text or ""):
        tag = m.group(1).lower().replace("_", "")
        if len(tag) >= 2 and tag not in seen:
            seen.append(tag)
    return seen[:15]


class PostCreateIn(BaseModel):
    content: str = Field(default="", max_length=2000)
    image_urls: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("content")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        return v


class PostUpdateIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class RepostIn(BaseModel):
    quote: str = Field(default="", max_length=2000)


class BuffIn(BaseModel):
    amount: int = Field(ge=1, le=10000)
    message: str = Field(default="", max_length=200)


class AuthorMiniOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    avatar_url: str | None = None
    frame: dict | None = None


class PostMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author: AuthorMiniOut
    content: str
    images: list[str] = []
    created_at: datetime


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author: AuthorMiniOut
    content: str
    images: list[str] = []
    repost_of_id: uuid.UUID | None = None
    repost_of: PostMini | None = None
    likes_count: int
    comments_count: int
    reposts_count: int
    saves_count: int
    buffs_count: int
    buffs_total_zyra: int
    is_edited: bool
    edited_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    my_flags: dict | None = None  # {liked, saved, reposted} for authed viewer


class PostActionOut(BaseModel):
    ok: bool = True
    likes_count: int | None = None
    saves_count: int | None = None
    reposts_count: int | None = None
    active: bool | None = None  # current state after action


class BuffOut(BaseModel):
    id: uuid.UUID
    amount: int
    message: str
    created_at: datetime
    sender: AuthorMiniOut
