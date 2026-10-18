"""VYRO — frame schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FrameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    description: str = ""
    rarity: str
    price_zyra: int
    is_active: bool
    is_limited: bool
    animation_type: str
    asset_url: str | None = None
    preview_url: str | None = None
    config: dict = {}
    created_at: datetime


class FrameOwnedOut(FrameOut):
    owned: bool = True
    source: str = "purchase"
    acquired_at: datetime | None = None


class FrameCreateIn(BaseModel):
    slug: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    rarity: str = Field(default="common", pattern=r"^(common|rare|epic|legendary)$")
    price_zyra: int = Field(default=0, ge=0, le=1_000_000)
    is_active: bool = True
    is_limited: bool = False
    animation_type: str = Field(default="css", pattern=r"^(css|image|video|lottie)$")
    asset_url: str | None = Field(default=None, max_length=500)
    preview_url: str | None = Field(default=None, max_length=500)
    config: dict = Field(default_factory=dict)


class FrameUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    price_zyra: int | None = Field(default=None, ge=0, le=1_000_000)
    is_active: bool | None = None
    config: dict | None = None


class PurchaseOut(BaseModel):
    ok: bool = True
    frame: FrameOut
    balance_zyra: int


class EquipOut(BaseModel):
    ok: bool = True
    equipped_frame_id: uuid.UUID | None = None
