"""VYRO — Wallet service (ZYRA economy core).

Design:
- Wallets locked with SELECT ... FOR UPDATE in deterministic order (no deadlocks).
- Ledger is append-only; every balance change writes a signed Transaction row.
- All public functions are atomic units (single commit) unless commit=False.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import BadRequest, InsufficientBalance, UserNotFound
from app.models import Transaction, User, Wallet
from app.models.base import utcnow
from app.models.wallet import TX_ADMIN_GRANT, TX_DAILY_BONUS, TX_SIGNUP_BONUS


async def ensure_wallet(db: AsyncSession, user_id: uuid.UUID) -> Wallet:
    wallet = (
        await db.execute(sa_select(Wallet).where(Wallet.user_id == user_id).with_for_update())
    ).scalar_one_or_none()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0)
        db.add(wallet)
        await db.flush()
    return wallet


async def _lock_two(db: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> tuple[Wallet, Wallet]:
    """Lock both wallets in deterministic (user_id) order to avoid deadlocks."""
    first, second = sorted([a, b], key=lambda x: str(x))
    w_first = (
        await db.execute(sa_select(Wallet).where(Wallet.user_id == first).with_for_update())
    ).scalar_one()
    w_second = None
    if second != first:
        w_second = (
            await db.execute(sa_select(Wallet).where(Wallet.user_id == second).with_for_update())
        ).scalar_one()
    sender_w = w_first if first == a else w_second
    recipient_w = w_first if first == b else w_second
    return sender_w, recipient_w


def _ledger(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: int,
    balance_after: int,
    type_: str,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
    counterparty_id: uuid.UUID | None = None,
    note: str = "",
) -> None:
    db.add(
        Transaction(
            user_id=user_id,
            amount=amount,
            balance_after=balance_after,
            type=type_,
            ref_type=ref_type,
            ref_id=ref_id,
            counterparty_id=counterparty_id,
            note=note,
        )
    )


async def credit(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: int,
    type_: str,
    *,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
    note: str = "",
    commit: bool = True,
) -> Wallet:
    if amount <= 0:
        raise BadRequest("مقدار باید مثبت باشد")
    wallet = await ensure_wallet(db, user_id)
    wallet.balance += amount
    wallet.total_earned += amount
    _ledger(
        db, user_id=user_id, amount=amount, balance_after=wallet.balance,
        type_=type_, ref_type=ref_type, ref_id=ref_id, note=note,
    )
    if commit:
        await db.commit()
    return wallet


async def transfer(
    db: AsyncSession,
    *,
    sender_id: uuid.UUID,
    recipient_id: uuid.UUID,
    amount: int,
    sent_type: str,
    received_type: str,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
    note: str = "",
    commit: bool = True,
) -> tuple[Wallet, Wallet]:
    """Atomic peer-to-peer ZYRA transfer."""
    if amount <= 0:
        raise BadRequest("مقدار باید مثبت باشد")
    if sender_id == recipient_id:
        raise BadRequest("ارسال به خودتان مجاز نیست")

    sender_w, recipient_w = await _lock_two(db, sender_id, recipient_id)
    if sender_w.balance < amount:
        raise InsufficientBalance()

    sender_w.balance -= amount
    sender_w.total_spent += amount
    recipient_w.balance += amount
    recipient_w.total_earned += amount

    _ledger(
        db, user_id=sender_id, amount=-amount, balance_after=sender_w.balance,
        type_=sent_type, ref_type=ref_type, ref_id=ref_id,
        counterparty_id=recipient_id, note=note,
    )
    _ledger(
        db, user_id=recipient_id, amount=amount, balance_after=recipient_w.balance,
        type_=received_type, ref_type=ref_type, ref_id=ref_id,
        counterparty_id=sender_id, note=note,
    )
    if commit:
        await db.commit()
    return sender_w, recipient_w


async def wallet_info(db: AsyncSession, me_id: uuid.UUID) -> dict:
    wallet = await ensure_wallet(db, me_id)
    next_daily = None
    if wallet.last_daily_at:
        next_daily = wallet.last_daily_at + timedelta(hours=settings.DAILY_BONUS_COOLDOWN_HOURS)
    return {
        "balance_zyra": wallet.balance,
        "total_earned": wallet.total_earned,
        "total_spent": wallet.total_spent,
        "last_daily_at": wallet.last_daily_at,
        "next_daily_bonus_at": next_daily,
    }


async def list_transactions(
    db: AsyncSession, me_id: uuid.UUID, cursor: tuple | None, limit: int
) -> dict:
    from app.schemas.common import decode_cursor, encode_cursor

    q = (
        select(Transaction, User, Wallet)
        .join(User, User.id == Transaction.counterparty_id, isouter=True)
        .join(Wallet, Wallet.user_id == User.id, isouter=True)
        .where(Transaction.user_id == me_id)
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        ts, id_ = cursor
        q = q.where((Transaction.created_at, Transaction.id) < (ts, id_))

    rows = (await db.execute(q)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    from app.models import Profile

    items = []
    for tx, cp_user, cp_wallet in rows:
        cp = None
        if cp_user:
            prof = (
                await db.execute(sa_select(Profile).where(Profile.user_id == cp_user.id))
            ).scalar_one_or_none()
            if prof:
                cp = {
                    "id": str(cp_user.id),
                    "username": prof.username,
                    "display_name": prof.display_name,
                    "avatar_url": prof.avatar_url,
                    "frame": None,
                }
        items.append({
            "id": str(tx.id),
            "amount": tx.amount,
            "balance_after": tx.balance_after,
            "type": tx.type,
            "ref_type": tx.ref_type,
            "ref_id": str(tx.ref_id) if tx.ref_id else None,
            "counterparty": cp,
            "note": tx.note,
            "created_at": tx.created_at,
        })
    next_cursor = (
        encode_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None
    )
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}


async def claim_daily_bonus(db: AsyncSession, me_id: uuid.UUID) -> dict:
    wallet = await ensure_wallet(db, me_id)
    now = utcnow()
    cooldown = timedelta(hours=settings.DAILY_BONUS_COOLDOWN_HOURS)
    if wallet.last_daily_at and (now - wallet.last_daily_at) < cooldown:
        remaining = int((cooldown - (now - wallet.last_daily_at)).total_seconds())
        raise BadRequest(
            f"پاداش روزانه قبلاً دریافت شده؛ {remaining // 3600} ساعت و {(remaining % 3600) // 60} دقیقه دیگر دوباره تلاش کنید",
            code="daily_already_claimed",
            details={"retry_after_seconds": remaining},
        )
    amount = settings.DAILY_BONUS_ZYRA
    wallet.last_daily_at = now
    await credit(
        db, me_id, amount, TX_DAILY_BONUS,
        note="پاداش روزانه", commit=False,
    )
    await db.commit()
    return {
        "ok": True,
        "amount_granted": amount,
        "balance_zyra": wallet.balance,
        "next_daily_bonus_at": now + cooldown,
    }


async def admin_grant(
    db: AsyncSession, *, target_user_id: uuid.UUID, amount: int, reason: str
) -> Wallet:
    return await credit(
        db, target_user_id, amount, TX_ADMIN_GRANT,
        note=reason or "اهدای ادمین",
    )


async def platform_stats(db: AsyncSession) -> dict:
    total_zyra = (
        await db.execute(sa_select(func.coalesce(func.sum(Wallet.balance), 0)))
    ).scalar()
    total_users = (await db.execute(sa_select(func.count(User.id)))).scalar()
    return {"zyra_in_circulation": int(total_zyra or 0), "users": int(total_users or 0)}
