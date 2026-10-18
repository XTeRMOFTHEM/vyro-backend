"""VYRO — ZYRA wallet, immutable transaction ledger, buffs & donations."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDPk, utcnow

# ---- ledger transaction types ----
TX_SIGNUP_BONUS = "signup_bonus"
TX_DAILY_BONUS = "daily_bonus"
TX_ADMIN_GRANT = "admin_grant"
TX_BUFF_SENT = "buff_sent"
TX_BUFF_RECEIVED = "buff_received"
TX_DONATION_SENT = "donation_sent"
TX_DONATION_RECEIVED = "donation_received"
TX_FRAME_PURCHASE = "frame_purchase"


class Wallet(Base, UUIDPk):
    __tablename__ = "wallets"
    __table_args__ = (CheckConstraint("balance >= 0", name="balance_non_negative"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, index=True, nullable=False,
    )
    balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_earned: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_spent: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_daily_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="wallet")  # noqa: F821


class Transaction(Base, UUIDPk):
    """Append-only ledger — never update, never delete."""

    __tablename__ = "transactions"
    __table_args__ = (Index("ix_tx_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # signed: + credit / - debit
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    ref_type: Mapped[str | None] = mapped_column(String(30), nullable=True)   # post|user|frame
    ref_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Buff(Base, UUIDPk):
    """Gift ZYRA gems on a post (boost / tip)."""

    __tablename__ = "buffs"
    __table_args__ = (
        Index("ix_buffs_post_created", "post_id", "created_at"),
        Index("ix_buffs_sender_created", "sender_id", "created_at"),
    )

    sender_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Donation(Base, UUIDPk):
    """Gift ZYRA directly to a user."""

    __tablename__ = "donations"
    __table_args__ = (
        Index("ix_donations_sender_created", "sender_id", "created_at"),
        Index("ix_donations_recipient_created", "recipient_id", "created_at"),
    )

    sender_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
