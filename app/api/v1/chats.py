"""VYRO — /api/v1/chats : conversations + messages (REST part of chat)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, Db, Page
from app.core.rate_limit import rate_limit
from app.schemas.chat import (
    ConversationActionOut, ConversationCreateIn, ConversationOut, MessageCreateIn,
    MessageEditIn, MessageOut, ReadOut,
)
from app.schemas.common import Ok, Page as PageModel
from app.services import chat_service
from app.ws.manager import manager

router = APIRouter(prefix="/chats", tags=["chats"])
_rl_msg = Depends(rate_limit("60/60", scope="ip:path"))


@router.get("", response_model=list[ConversationOut])
async def list_chats(me: CurrentUser, db: Db, limit: int = 50, offset: int = 0):
    return await chat_service.list_conversations(db, me, limit, offset)


@router.post("", response_model=ConversationActionOut, status_code=201)
async def create_or_get(body: ConversationCreateIn, me: CurrentUser, db: Db):
    conv, partner_profile, created = await chat_service.get_or_create_conversation(
        db, me, username=body.username, user_id=body.user_id
    )
    from app.services.user_service import author_mini

    return {
        "conversation_id": conv.id,
        "created": created,
        "partner": author_mini(partner_profile),
    }


@router.get("/{conversation_id}/messages", response_model=PageModel)
async def history(conversation_id: uuid.UUID, me: CurrentUser, db: Db, page: Page):
    return await chat_service.messages(
        db, me, conversation_id, page.decoded_cursor, page.limit
    )


@router.post("/{conversation_id}/messages", response_model=MessageOut, status_code=201, dependencies=[_rl_msg])
async def send(conversation_id: uuid.UUID, body: MessageCreateIn, me: CurrentUser, db: Db):
    payload, member_ids = await chat_service.send_message(
        db, me, conversation_id, body.content, body.reply_to_id
    )
    payload["client_id"] = body.client_id
    # realtime fan-out (best-effort, outside tx)
    await manager.broadcast_to_conversation(
        member_ids, {"type": "message.new", "message": payload}
    )
    return payload


@router.post("/{conversation_id}/read", response_model=ReadOut)
async def mark_read(conversation_id: uuid.UUID, me: CurrentUser, db: Db):
    result = await chat_service.mark_read(db, me, conversation_id)
    member_ids = await chat_service._member_ids(db, conversation_id)
    await manager.broadcast_to_conversation(
        member_ids,
        {
            "type": "read",
            "conversation_id": str(conversation_id),
            "user_id": str(me.id),
            "last_read_at": result["last_read_at"].isoformat(),
        },
    )
    return result


@router.patch("/messages/{message_id}", response_model=dict)
async def edit_message(message_id: uuid.UUID, body: MessageEditIn, me: CurrentUser, db: Db):
    result = await chat_service.edit_message(db, me, message_id, body.content)
    await manager.broadcast_to_conversation(
        result["member_ids"],
        {"type": "message.edited", "message": result["payload"]},
    )
    return result["payload"]


@router.delete("/messages/{message_id}", response_model=Ok)
async def delete_message(message_id: uuid.UUID, me: CurrentUser, db: Db):
    result = await chat_service.delete_message(db, me, message_id)
    await manager.broadcast_to_conversation(
        result["member_ids"], {"type": "message.deleted", "message": result["payload"]}
    )
    return Ok()
