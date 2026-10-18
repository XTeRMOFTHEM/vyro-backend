"""VYRO — Frame service: catalog, purchase with ZYRA, inventory, equip."""
from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.cache import KEY_FRAMES_CATALOG, cache
from app.core.errors import BadRequest, Conflict, FrameNotFound
from app.models import Frame, Profile, UserFrame
from app.models.base import utcnow
from app.models.wallet import TX_FRAME_PURCHASE
from app.services import notification_service, user_service, wallet_service
from app.services.user_service import frame_to_dict


async def catalog_dict(db: AsyncSession, force_refresh: bool = False) -> list[dict]:
    async def _load():
        rows = (
            await db.execute(
                select(Frame).where(Frame.is_active.is_(True)).order_by(Frame.price_zyra.asc())
            )
        ).scalars().all()
        return [
            {
                "id": str(f.id),
                "slug": f.slug,
                "name": f.name,
                "description": f.description,
                "rarity": f.rarity,
                "price_zyra": f.price_zyra,
                "is_active": f.is_active,
                "is_limited": f.is_limited,
                "animation_type": f.animation_type,
                "asset_url": f.asset_url,
                "preview_url": f.preview_url,
                "config": f.config or {},
                "created_at": f.created_at,
            }
            for f in rows
        ]

    if force_refresh:
        data = await _load()
        await cache.set(KEY_FRAMES_CATALOG, data, ttl=300)
        return data
    return await cache.get_or_set(KEY_FRAMES_CATALOG, _load, ttl=300) or []


async def get_frame(db: AsyncSession, frame_id: uuid.UUID) -> Frame:
    frame = (await db.execute(select(Frame).where(Frame.id == frame_id))).scalar_one_or_none()
    if not frame:
        raise FrameNotFound()
    return frame


async def get_frame_by_slug(db: AsyncSession, slug: str) -> Frame | None:
    return (
        await db.execute(select(Frame).where(Frame.slug == slug))
    ).scalar_one_or_none()


async def purchase(db: AsyncSession, me: User, frame_id: uuid.UUID) -> dict:
    frame = await get_frame(db, frame_id)
    if not frame.is_active:
        raise BadRequest("این فریم در حال حاضر قابل خرید نیست", code="frame_inactive")

    owned = (
        await db.execute(
            select(UserFrame).where(UserFrame.user_id == me.id, UserFrame.frame_id == frame.id)
        )
    ).scalar_one_or_none()
    if owned:
        raise Conflict("این فریم از قبل در مجموعه شماست", code="already_owned")

    wallet = await wallet_service.ensure_wallet(db, me.id)
    if wallet.balance < frame.price_zyra:
        raise BadRequest(
            f"موجودی ZYRA کافی نیست (قیمت: {frame.price_zyra} / موجودی: {wallet.balance})",
            code="insufficient_balance",
        )

    from app.services.wallet_service import _ledger

    # atomic debit + ledger
    wallet.balance -= frame.price_zyra
    wallet.total_spent += frame.price_zyra
    _ledger(
        db,
        user_id=me.id,
        amount=-frame.price_zyra,
        balance_after=wallet.balance,
        type_=TX_FRAME_PURCHASE,
        ref_type="frame",
        ref_id=frame.id,
        note=f"خرید فریم {frame.name}",
    )
    db.add(UserFrame(user_id=me.id, frame_id=frame.id, source="purchase"))
    await db.flush()
    await notification_service.notify(
        db,
        recipient_id=me.id,
        type_=notification_service.TYPE_FRAME_PURCHASE,
        ref_type="frame",
        ref_id=frame.id,
        data={"frame_name": frame.name, "price": frame.price_zyra},
    )
    await db.commit()
    return {
        "ok": True,
        "frame": frame_to_dict(frame),
        "balance_zyra": wallet.balance,
    }


async def inventory(db: AsyncSession, me: User) -> list[dict]:
    rows = (
        await db.execute(
            select(UserFrame, Frame)
            .join(Frame, Frame.id == UserFrame.frame_id)
            .where(UserFrame.user_id == me.id)
            .order_by(UserFrame.acquired_at.desc())
        )
    ).all()
    equipped_id = me.profile.equipped_frame_id
    return [
        {
            **frame_to_dict(f),
            "owned": True,
            "source": uf.source,
            "acquired_at": uf.acquired_at,
            "equipped": equipped_id == f.id,
        }
        for uf, f in rows
    ]


async def equip(db: AsyncSession, me: User, frame_id: uuid.UUID | None) -> dict:
    profile: Profile = me.profile
    if frame_id is None:
        profile.equipped_frame_id = None
        await db.commit()
        await cache.delete(KEY_FRAMES_CATALOG)
        return {"ok": True, "equipped_frame_id": None}

    frame = await get_frame(db, frame_id)
    owned = (
        await db.execute(
            select(UserFrame.id).where(UserFrame.user_id == me.id, UserFrame.frame_id == frame.id)
        )
    ).scalar_one_or_none()
    if not owned:
        raise BadRequest("این فریم در مجموعه شما نیست؛ ابتدا خریداری کنید", code="frame_not_owned")
    profile.equipped_frame_id = frame.id
    await db.commit()
    return {"ok": True, "equipped_frame_id": str(frame.id)}


# ---------------- admin ----------------

async def admin_create_frame(db: AsyncSession, data: dict) -> Frame:
    if await get_frame_by_slug(db, data["slug"]):
        raise Conflict("فریمی با این slug وجود دارد", code="slug_taken")
    frame = Frame(**data)
    db.add(frame)
    await db.commit()
    await catalog_dict(db, force_refresh=True)
    return frame


async def admin_update_frame(db: AsyncSession, frame_id: uuid.UUID, data: dict) -> Frame:
    frame = await get_frame(db, frame_id)
    for k, v in data.items():
        if v is not None:
            setattr(frame, k, v)
    await db.commit()
    await catalog_dict(db, force_refresh=True)
    return frame
