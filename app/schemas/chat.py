"""VYRO — chat schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.post import AuthorMiniOut


class ConversationCreateIn(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=20)
    user_id: uuid.UUID | None = None


class MessageCreateIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    reply_to_id: uuid.UUID | None = None
    client_id: str | None = Field(default=None, max_length=64)  # client-side dedup/echo


class MessageEditIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class MessageMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sender_id: uuid.UUID
    content: str
    is_deleted: bool
    created_at: datetime


class MessageOut(MessageMini):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: uuid.UUID
    sender: AuthorMiniOut
    reply_to: dict | None = None  # {id, sender_username, content_preview}
    edited_at: datetime | None = None
    client_id: str | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partner: AuthorMiniOut
    partner_online: bool = False
    last_message: dict | None = None  # {id, content, sender_id, created_at, is_deleted}
    unread_count: int = 0
    last_message_at: datetime | None = None
    created_at: datetime


class ConversationActionOut(BaseModel):
    conversation_id: uuid.UUID
    created: bool  # True if newly created
    partner: AuthorMiniOut


class ReadOut(BaseModel):
    ok: bool = True
    last_read_at: datetime
