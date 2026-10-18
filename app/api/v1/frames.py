"""VYRO — /api/v1/frames : catalog, purchase, inventory."""
from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, Db
from app.core.errors import BadRequest
from app.schemas.frame import FrameOut, FrameOwnedOut, PurchaseOut
from app.services import frame_service, user_service

router = APIRouter(prefix="/frames", tags=["frames"])


@router.get("", response_model=list[FrameOut])
async def catalog(db: Db):
    return await frame_service.catalog_dict(db)


@router.get("/inventory", response_model=list[FrameOwnedOut])
async def my_frames(me: CurrentUser, db: Db):
    return await frame_service.inventory(db, me)


@router.get("/{frame_id}", response_model=FrameOut)
async def get_frame(frame_id: uuid.UUID, db: Db):
    frame = await frame_service.get_frame(db, frame_id)
    return user_service.frame_to_dict(frame)


@router.post("/{frame_id}/purchase", response_model=PurchaseOut)
async def purchase(frame_id: uuid.UUID, me: CurrentUser, db: Db):
    return await frame_service.purchase(db, me, frame_id)
