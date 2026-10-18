"""VYRO — Notifications."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import UUIDPk, utcnow

TYPE_FOLLOW = "follow"
TYPE_LIKE = "like"
TYPE_COMMENT = "comment"
TYPE_COMMENT_REPLY = "comment_reply"
TYPE_COMMENT_LIKE = "comment_like"
TYPE_REPOST = "repost"
TYPE_BUFF = "buff"
TYPE_DONATION = "donation"
TYPE_FRAME_PURCHASE = "frame_purchase"
TYPE_SYSTEM = "system"


class Notification(Base, UUIDPk):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notif_recipient_created", "recipient_id", "created_at"),
        Index("ix_notif_recipient_read", "recipient_id", "is_read"),
    )

    recipient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    ref_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # post|comment|user|frame
    ref_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False, server_default="{}")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
