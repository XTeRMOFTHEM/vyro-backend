"""VYRO — /api/v1/users : profile, avatar/banner, follow, donate, username."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import CurrentUser, Db, OptionalUser, Page
from app.core.errors import BadRequest
from app.core.rate_limit import rate_limit
from app.core.storage import storage
from app.schemas.common import Page as PageModel
from app.schemas.frame import EquipOut, FrameOut
from app.schemas.user import (
    DonateIn, DonateOut, EquipFrameIn, FollowActionOut,
    ProfileMe, ProfilePublic, ProfileUpdateIn, UsernameUpdateIn,
)
from app.services import (
    follow_service, frame_service, post_service, user_service, wallet_service,
)

router = APIRouter(prefix="/users", tags=["users"])


# ---------- me (static routes BEFORE /{username}) ----------

@router.get("/me", response_model=ProfileMe)
async def me(me: CurrentUser, db: Db):
    return await user_service.me_dict(db, me)


@router.patch("/me", response_model=ProfileMe)
async def update_me(body: ProfileUpdateIn, me: CurrentUser, db: Db):
    return await user_service.update_profile(db, me, body.display_name, body.bio)


@router.put("/me/username", response_model=ProfileMe)
async def update_username(body: UsernameUpdateIn, me: CurrentUser, db: Db):
    return await user_service.change_username(db, me, body.username)


@router.put("/me/avatar", response_model=ProfileMe)
async def upload_avatar(me: CurrentUser, db: Db, file: UploadFile = File(...)):
    url = await storage.save_image(file, "avatars")
    return await user_service.set_avatar(db, me, url)


@router.put("/me/banner", response_model=ProfileMe)
async def upload_banner(me: CurrentUser, db: Db, file: UploadFile = File(...)):
    url = await storage.save_image(file, "banners")
    return await user_service.set_banner(db, me, url)


@router.put("/me/frame", response_model=EquipOut)
async def equip_frame(body: EquipFrameIn, me: CurrentUser, db: Db):
    return await frame_service.equip(db, me, body.frame_id)


# ---------- public ----------

@router.get("/{username}", response_model=ProfilePublic)
async def get_profile(username: str, viewer: OptionalUser, db: Db):
    profile = await user_service.get_profile_by_username(db, username)
    return await user_service.profile_public_dict(db, profile, viewer.id if viewer else None)


@router.get("/{username}/posts", response_model=PageModel)
async def user_posts(username: str, viewer: OptionalUser, db: Db, page: Page):
    return await post_service.user_posts(
        db, viewer.id if viewer else None, username, page.decoded_cursor, page.limit
    )


@router.get("/{username}/followers", response_model=PageModel)
async def followers(username: str, db: Db, page: Page):
    profile = await user_service.get_profile_by_username(db, username)
    return await user_service.followers_list(db, profile, page.decoded_cursor, page.limit)


@router.get("/{username}/following", response_model=PageModel)
async def following(username: str, db: Db, page: Page):
    profile = await user_service.get_profile_by_username(db, username)
    return await user_service.following_list(db, profile, page.decoded_cursor, page.limit)


@router.post("/{username}/follow", response_model=FollowActionOut)
async def follow(username: str, me: CurrentUser, db: Db):
    return await follow_service.follow(db, me.id, username)


@router.delete("/{username}/follow", response_model=FollowActionOut)
async def unfollow(username: str, me: CurrentUser, db: Db):
    return await follow_service.unfollow(db, me.id, username)


@router.post("/{username}/donate", response_model=DonateOut, dependencies=[Depends(rate_limit("20/60"))])
async def donate(username: str, body: DonateIn, me: CurrentUser, db: Db):
    profile = await user_service.get_profile_by_username(db, username)
    if profile.user_id == me.id:
        raise BadRequest("نمی‌توانید به خودتان دونیت کنید")
    sender_w, _ = await wallet_service.transfer(
        db,
        sender_id=me.id,
        recipient_id=profile.user_id,
        amount=body.amount,
        sent_type="donation_sent",
        received_type="donation_received",
        ref_type="user",
        ref_id=profile.user_id,
        note=body.message or "دونیت",
    )
    from app.services import notification_service
    from app.models.notification import TYPE_DONATION

    await notification_service.notify(
        db,
        recipient_id=profile.user_id,
        type_=TYPE_DONATION,
        actor_id=me.id,
        ref_type="user",
        ref_id=me.id,
        data={
            "actor_username": me.profile.username,
            "amount": body.amount,
            "message": body.message,
        },
    )
    await db.commit()
    return DonateOut(amount=body.amount, recipient_id=profile.user_id, sender_balance=sender_w.balance)
