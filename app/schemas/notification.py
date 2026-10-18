"""VYRO — notification schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.post import AuthorMiniOut


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    actor: AuthorMiniOut | None = None
    ref_type: str | None = None
    ref_id: uuid.UUID | None = None
    data: dict = {}
    is_read: bool
    created_at: datetime


class ReadAllOut(BaseModel):
    ok: bool = True
    marked: int


class UnreadCountOut(BaseModel):
    unread_count: int
