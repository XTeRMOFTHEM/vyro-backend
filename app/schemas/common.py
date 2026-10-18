"""VYRO — shared schemas: pagination (keyset cursor), page envelope, minis."""
from __future__ import annotations

import base64
import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from app.core.errors import BadRequest

T = TypeVar("T")


# ---------------- keyset cursor ----------------

def encode_cursor(ts: datetime, id_: uuid.UUID) -> str:
    raw = f"{ts.isoformat()}|{id_}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        pad = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + pad).encode()).decode()
        ts_raw, id_raw = raw.split("|", 1)
        return datetime.fromisoformat(ts_raw), uuid.UUID(id_raw)
    except Exception as e:
        raise BadRequest("کرسر صفحه‌بندی نامعتبر است", code="invalid_cursor") from e


# ---------------- envelopes ----------------

class Page(BaseModel, Generic[T]):
    items: list[T] = []
    next_cursor: str | None = None
    has_more: bool = False


class Ok(BaseModel):
    ok: bool = True


class AuthorMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    avatar_url: str | None = None
    frame: dict | None = None


class CursorOut(BaseModel):
    cursor: str | None
