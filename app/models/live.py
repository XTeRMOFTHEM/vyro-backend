"""VYRO — Live streaming (placeholder core for future integration).

Models & basic lifecycle APIs exist now; RTMP/WebRTC ingest + viewers,
chat-over-live and gifts-over-live will plug into this later.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPk, utcnow

STATUS_SCHEDULED = "scheduled"
STATUS_LIVE = "live"
STATUS_ENDED = "ended"


class LiveStream(Base, UUIDPk, TimestampMixin):
    __tablename__ = "live_streams"
    __table_args__ = (Index("ix_live_status_created", "status", "created_at"),)

    host_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=STATUS_SCHEDULED, nullable=False)
    stream_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    viewer_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    peak_viewers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False, server_default="{}")


def new_stream_key() -> str:
    return f"live_{secrets.token_urlsafe(32)}"
