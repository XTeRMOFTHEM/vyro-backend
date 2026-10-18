"""VYRO — /api/v1/wallet : ZYRA balance, ledger, daily bonus."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, Db, Page
from app.schemas.common import Page as PageModel
from app.schemas.wallet import DailyBonusOut, TransactionOut, WalletOut
from app.services import wallet_service

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("", response_model=WalletOut)
async def my_wallet(me: CurrentUser, db: Db):
    return await wallet_service.wallet_info(db, me.id)


@router.get("/transactions", response_model=PageModel)
async def transactions(me: CurrentUser, db: Db, page: Page):
    return await wallet_service.list_transactions(
        db, me.id, page.decoded_cursor, page.limit
    )


@router.post("/daily", response_model=DailyBonusOut)
async def daily_bonus(me: CurrentUser, db: Db):
    return await wallet_service.claim_daily_bonus(db, me.id)
