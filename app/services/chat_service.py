"""VYRO — Chat service: DM conversations, messages with reply, read receipts.

Realtime delivery happens in the WS layer; this service guarantees the
durable state (conversation membership, messages, unread) is always correct
even if the client is offline.
"""
from __future__ import annotations

import uuid

from sqlalchemy import and_, distinct, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import conv_members_key, cache
from app.core.errors import (
    BadRequest,
    ConversationNotFound,
    Forbidden,
    MessageNotFound,
    UserNotFound,
)
from app.models import Conversation, ConversationParticipant, Message, Profile, User
from app.models.base import utcnow
from app.services import user_service
from app.services.user_service import author_mini


async def _member_ids(db: AsyncSession, conversation_id: uuid.UUID) -> set[uuid.UUID]:
    cached = await cache.get(conv_members_key(str(conversation_id)))
    if cached:
        return {uuid.UUID(x) for x in cached}
    rows = (
        await db.execute(
            select(ConversationParticipant.user_id).where(
                ConversationParticipant.conversation_id == conversation_id
            )
        )
    ).scalars().all()
    ids = set(rows)
    await cache.set(conv_members_key(str(conversation_id)), [str(x) for x in ids], ttl=120)
    return ids


async def assert_member(db: AsyncSession, conversation_id: uuid.UUID, me_id: uuid.UUID) -> None:
    ids = await _member_ids(db, conversation_id)
    if me_id not in ids:
        raise Forbidden("به این گفتگو دسترسی ندارید")


async def get_or_create_conversation(
    db: AsyncSession, me: User, *, username: str | None = None, user_id: uuid.UUID | None = None
) -> tuple[Conversation, Profile, bool]:
    target_profile = None
    if username:
        target_profile = await user_service.get_profile_by_username(db, username)
    elif user_id:
        target_profile = (
            await db.execute(select(Profile).where(Profile.user_id == user_id))
        ).scalar_one_or_none()
        if not target_profile:
            raise UserNotFound()
    else:
        raise BadRequest("username یا user_id لازم است")

    if target_profile.user_id == me.id:
        raise BadRequest("نمی‌توانید با خودتان گفتگو بسازید")

    # find existing 1-1 conversation containing exactly both users
    cp1 = ConversationParticipant
    q = (
        select(Conversation.id)
        .join(cp1, cp1.conversation_id == Conversation.id)
        .where(cp1.user_id == me.id)
        .intersect(
            select(Conversation.id)
            .join(cp1, cp1.conversation_id == Conversation.id)
            .where(cp1.user_id == target_profile.user_id)
        )
    )
    candidates = (await db.execute(q)).scalars().all()
    if candidates:
        for cid in candidates:
            ids = await _member_ids(db, cid)
            if len(ids) == 2 and target_profile.user_id in ids and me.id in ids:
                conv = (
                    await db.execute(select(Conversation).where(Conversation.id == cid))
                ).scalar_one()
                return conv, target_profile, False

    conv = Conversation()
    db.add(conv)
    await db.flush()
    db.add(ConversationParticipant(conversation_id=conv.id, user_id=me.id))
    db.add(ConversationParticipant(conversation_id=conv.id, user_id=target_profile.user_id))
    await db.commit()
    await cache.set(
        conv_members_key(str(conv.id)), [str(me.id), str(target_profile.user_id)], ttl=120
    )
    return conv, target_profile, True


async def list_conversations(db: AsyncSession, me: User, limit: int = 50, offset: int = 0) -> list[dict]:
    my_cp = ConversationParticipant
    convs = (
        await db.execute(
            select(Conversation, my_cp)
            .join(my_cp, my_cp.conversation_id == Conversation.id)
            .where(my_cp.user_id == me.id)
            .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    if not convs:
        return []
    conv_ids = [c.id for c, _ in convs]

    # other participants + profiles
    others = (
        await db.execute(
            select(ConversationParticipant, Profile)
            .join(Profile, Profile.user_id == ConversationParticipant.user_id)
            .where(
                ConversationParticipant.conversation_id.in_(conv_ids),
                ConversationParticipant.user_id != me.id,
            )
        )
    ).all()
    partner_by_conv = {cp.conversation_id: (cp, p) for cp, p in others}

    # unread counts (single grouped query)
    unread_rows = (
        await db.execute(
            select(Message.conversation_id, func.count(Message.id))
            .join(
                my_cp,
                and_(
                    my_cp.conversation_id == Message.conversation_id,
                    my_cp.user_id == me.id,
                ),
            )
            .where(
                Message.conversation_id.in_(conv_ids),
                Message.sender_id != me.id,
                Message.is_deleted.is_(False),
                or_(
                    my_cp.last_read_at.is_(None),
                    Message.created_at > my_cp.last_read_at,
                ),
            )
            .group_by(Message.conversation_id)
        )
    ).all()
    unread_by_conv = {cid: cnt for cid, cnt in unread_rows}

    # last message per conversation (DISTINCT ON)
    last_msgs = (
        await db.execute(
            select(Message)
            .distinct(Message.conversation_id)
            .where(Message.conversation_id.in_(conv_ids))
            .order_by(Message.conversation_id, Message.created_at.desc())
        )
    ).scalars().all()
    last_by_conv = {m.conversation_id: m for m in last_msgs}

    from app.ws.manager import manager

    items = []
    for conv, my_part in convs:
        partner = partner_by_conv.get(conv.id)
        if not partner:
            continue
        _cp_other, p_profile = partner
        lm = last_by_conv.get(conv.id)
        items.append({
            "id": str(conv.id),
            "partner": author_mini(p_profile),
            "partner_online": manager.is_online(p_profile.user_id),
            "last_message": (
                {
                    "id": str(lm.id),
                    "sender_id": str(lm.sender_id),
                    "content": "" if lm.is_deleted else lm.content,
                    "is_deleted": lm.is_deleted,
                    "created_at": lm.created_at,
                }
                if lm
                else None
            ),
            "unread_count": unread_by_conv.get(conv.id, 0),
            "last_message_at": conv.last_message_at,
            "created_at": conv.created_at,
        })
    return items


async def messages(
    db: AsyncSession, me: User, conversation_id: uuid.UUID, cursor, limit: int
) -> dict:
    from app.schemas.common import encode_cursor

    await assert_member(db, conversation_id, me.id)

    q = (
        select(Message, Profile)
        .join(Profile, Profile.user_id == Message.sender_id)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        ts, id_ = cursor
        q = q.where((Message.created_at, Message.id) < (ts, id_))
    rows = (await db.execute(q)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    # replies
    reply_ids = [m.reply_to_id for m, _ in rows if m.reply_to_id]
    reply_map = {}
    if reply_ids:
        rrows = (
            await db.execute(
                select(Message, Profile)
                .join(Profile, Profile.user_id == Message.sender_id)
                .where(Message.id.in_(reply_ids))
            )
        ).all()
        for rm, rp in rrows:
            reply_map[rm.id] = {
                "id": str(rm.id),
                "sender_username": rp.username,
                "content_preview": ("" if rm.is_deleted else (rm.content or ""))[:120],
            }

    items = []
    for m, p in rows:
        items.append({
            "id": str(m.id),
            "conversation_id": str(m.conversation_id),
            "sender": author_mini(p),
            "sender_id": str(m.sender_id),
            "content": "" if m.is_deleted else m.content,
            "reply_to": reply_map.get(m.reply_to_id),
            "reply_to_id": str(m.reply_to_id) if m.reply_to_id else None,
            "is_deleted": m.is_deleted,
            "edited_at": m.edited_at,
            "created_at": m.created_at,
            "client_id": None,
        })
    return {
        "items": items,
        "next_cursor": encode_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None,
        "has_more": has_more,
    }


async def send_message(
    db: AsyncSession, me: User, conversation_id: uuid.UUID,
    content: str, reply_to_id: uuid.UUID | None,
) -> tuple[dict, set[uuid.UUID]]:
    """Persist message; returns (payload, member_ids) for WS broadcast."""
    await assert_member(db, conversation_id, me.id)
    content = content.strip()
    if not content:
        raise BadRequest("متن پیام خالی است")

    if reply_to_id:
        target = (
            await db.execute(
                select(Message).where(
                    Message.id == reply_to_id, Message.conversation_id == conversation_id
                )
            )
        ).scalar_one_or_none()
        if not target:
            raise BadRequest("پیام پاسخ نامعتبر است", code="invalid_reply_to")

    msg = Message(
        conversation_id=conversation_id,
        sender_id=me.id,
        content=content,
        reply_to_id=reply_to_id,
    )
    db.add(msg)
    await db.flush()

    conv = (
        await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    ).scalar_one()
    conv.last_message_at = msg.created_at
    conv.last_message_preview = content[:200]

    # hydrate reply_to for the payload
    reply_to_payload = None
    if reply_to_id:
        target_row = (
            await db.execute(
                select(Message, Profile)
                .join(Profile, Profile.user_id == Message.sender_id)
                .where(Message.id == reply_to_id)
            )
        ).first()
        if target_row:
            tmsg, tprof = target_row
            reply_to_payload = {
                "id": str(tmsg.id),
                "sender_username": tprof.username,
                "content_preview": ("" if tmsg.is_deleted else (tmsg.content or ""))[:120],
            }

    # auto-read for sender
    await db.execute(
        update(ConversationParticipant)
        .where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == me.id,
        )
        .values(last_read_at=utcnow())
    )
    await db.commit()

    profile = me.profile
    payload = {
        "id": str(msg.id),
        "conversation_id": str(conversation_id),
        "sender": author_mini(profile),
        "sender_id": str(me.id),
        "content": msg.content,
        "reply_to": reply_to_payload,
        "reply_to_id": str(reply_to_id) if reply_to_id else None,
        "is_deleted": False,
        "edited_at": None,
        "created_at": msg.created_at,
        "client_id": None,
    }
    member_ids = await _member_ids(db, conversation_id)
    # invalidate member cache? membership unchanged; fine.
    return payload, member_ids


async def mark_read(db: AsyncSession, me: User, conversation_id: uuid.UUID) -> dict:
    await assert_member(db, conversation_id, me.id)
    now = utcnow()
    await db.execute(
        update(ConversationParticipant)
        .where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == me.id,
        )
        .values(last_read_at=now)
    )
    await db.commit()
    return {"ok": True, "last_read_at": now}


async def edit_message(db: AsyncSession, me: User, message_id: uuid.UUID, content: str) -> dict:
    msg = (
        await db.execute(select(Message).where(Message.id == message_id))
    ).scalar_one_or_none()
    if not msg:
        raise MessageNotFound()
    if msg.sender_id != me.id:
        raise Forbidden("فقط فرستنده می‌تواند پیام را ویرایش کند")
    if msg.is_deleted:
        raise BadRequest("پیام حذف‌شده قابل ویرایش نیست")
    msg.content = content.strip()
    msg.edited_at = utcnow()
    conv = (
        await db.execute(select(Conversation).where(Conversation.id == msg.conversation_id))
    ).scalar_one()
    conv.last_message_preview = msg.content[:200]
    await db.commit()
    profile = me.profile
    payload = {
        "id": str(msg.id),
        "conversation_id": str(msg.conversation_id),
        "sender": author_mini(profile),
        "sender_id": str(me.id),
        "content": msg.content,
        "is_deleted": False,
        "edited_at": msg.edited_at,
        "created_at": msg.created_at,
        "event": "message.edited",
    }
    member_ids = await _member_ids(db, msg.conversation_id)
    return {"payload": payload, "member_ids": member_ids}


async def delete_message(db: AsyncSession, me: User, message_id: uuid.UUID) -> dict:
    msg = (
        await db.execute(select(Message).where(Message.id == message_id))
    ).scalar_one_or_none()
    if not msg:
        raise MessageNotFound()
    if msg.sender_id != me.id:
        raise Forbidden("فقط فرستنده می‌تواند پیام را حذف کند")
    msg.is_deleted = True
    await db.commit()
    member_ids = await _member_ids(db, msg.conversation_id)
    return {
        "payload": {
            "id": str(msg.id),
            "conversation_id": str(msg.conversation_id),
            "event": "message.deleted",
        },
        "member_ids": member_ids,
    }
