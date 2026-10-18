"""VYRO — wallet / ZYRA schemas."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.post import AuthorMiniOut


class WalletOut(BaseModel):
    balance_zyra: int
    total_earned: int
    total_spent: int
    last_daily_at: datetime | None = None
    next_daily_bonus_at: datetime | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount: int
    balance_after: int
    type: str
    ref_type: str | None = None
    ref_id: uuid.UUID | None = None
    counterparty: AuthorMiniOut | None = None
    note: str = ""
    created_at: datetime


class DailyBonusOut(BaseModel):
    ok: bool = True
    amount_granted: int
    balance_zyra: int
    next_daily_bonus_at: datetime


class GrantIn(BaseModel):
    username: str | None = None
    user_id: uuid.UUID | None = None
    amount: int = Field(ge=1, le=1_000_000)
    reason: str = Field(default="", max_length=200)
