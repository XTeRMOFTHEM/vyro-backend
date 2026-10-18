"""VYRO — user/profile schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FrameMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    rarity: str
    animation_type: str
    asset_url: str | None = None
    preview_url: str | None = None
    config: dict = {}


class ProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    bio: str = ""
    avatar_url: str | None = None
    banner_url: str | None = None
    frame: FrameMini | None = None
    followers_count: int
    following_count: int
    posts_count: int
    is_verified: bool = False
    created_at: datetime
    # contextual (only when authed viewer)
    is_following: bool | None = None
    is_self: bool | None = None


class ProfileMe(ProfilePublic):
    email: str
    role: str
    is_email_verified: bool
    wallet: dict = {}


class ProfileUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=50)
    bio: str | None = Field(default=None, max_length=300)

    @field_validator("display_name")
    @classmethod
    def clean_dn(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class UsernameUpdateIn(BaseModel):
    username: str = Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9_]+$")

    @field_validator("username")
    @classmethod
    def normalize(cls, v: str) -> str:
        from app.schemas.auth import USERNAME_RE, RESERVED_USERNAMES
        v = v.strip().lower()
        if not USERNAME_RE.match(v):
            raise ValueError("نام کاربری فقط حروف انگلیسی، عدد و _ (۳ تا ۲۰ کاراکتر)")
        if v in RESERVED_USERNAMES:
            raise ValueError("این نام کاربری مجاز نیست")
        return v


class EquipFrameIn(BaseModel):
    frame_id: uuid.UUID | None = None  # null = unequip


class FollowActionOut(BaseModel):
    following: bool
    followers_count: int


class DonateIn(BaseModel):
    amount: int = Field(ge=1, le=1_000_000)
    message: str = Field(default="", max_length=200)


class DonateOut(BaseModel):
    ok: bool = True
    amount: int
    recipient_id: uuid.UUID
    sender_balance: int
