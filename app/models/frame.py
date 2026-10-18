"""VYRO — Profile frames (animated borders) & inventory.

Frame rendering contract for frontends (Flutter / Web):
    animation_type: "css" | "image" | "video" | "lottie"
    - css    -> render config["css"] around avatar; config["keyframes"] = CSS @keyframes
    - image  -> overlay config/asset_url (webp/gif) around avatar
    - video  -> asset_url (mp4/webm loop, muted)
    - lottie -> asset_url (lottie json)
`config` is a free-form JSONB so new animation kinds can ship without migrations.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPk, utcnow
from datetime import datetime

RARITY_COMMON = "common"
RARITY_RARE = "rare"
RARITY_EPIC = "epic"
RARITY_LEGENDARY = "legendary"


class Frame(Base, UUIDPk, TimestampMixin):
    __tablename__ = "frames"

    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    rarity: Mapped[str] = mapped_column(String(20), default=RARITY_COMMON, nullable=False, index=True)
    price_zyra: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_limited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    animation_type: Mapped[str] = mapped_column(String(20), default="css", nullable=False)
    asset_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False, server_default="{}")


class UserFrame(Base, UUIDPk):
    """Owned frames inventory."""

    __tablename__ = "user_frames"
    __table_args__ = (UniqueConstraint("user_id", "frame_id", name="uq_user_frames_pair"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    frame_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("frames.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), default="purchase", nullable=False)  # purchase|admin|gift
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    frame: Mapped[Frame] = relationship(lazy="selectin")
