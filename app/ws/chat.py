"""VYRO — Chat WebSocket endpoint.

Connect:  ws://host/ws/chat?token=<ACCESS_TOKEN>
Client -> Server JSON frames:
    {"type":"message","conversation_id":"...","content":"...","reply_to_id":null,"client_id":"c1"}
    {"type":"typing","conversation_id":"..."}
    {"type":"read","conversation_id":"..."}
    {"type":"ping"}
Server -> Client frames:
    {"type":"message.new","message":{...}}
    {"type":"message.sent","client_id":"c1","message":{...}}   (echo to sender devices)
    {"type":"typing","conversation_id":"...","user_id":"..."}
    {"type":"read","conversation_id":"...","user_id":"...","last_read_at":"..."}
    {"type":"message.edited","message":{...}}
    {"type":"message.deleted","message":{...}}
    {"type":"notification","notification":{...}}
    {"type":"pong"}
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.models import User
from app.services import chat_service
from app.ws.manager import jsonable, manager

logger = logging.getLogger("vyro.ws")

router = APIRouter()


async def _auth(token: str) -> uuid.UUID | None:
    try:
        payload = decode_access_token(token)
        return uuid.UUID(payload["sub"])
    except Exception:
        return None


async def _run_frame(websocket: WebSocket, user_id: uuid.UUID, raw: dict) -> None:
    """Handle one client frame (own DB session per frame)."""
    mtype = raw.get("type")

    if mtype == "ping":
        await websocket.send_json({"type": "pong"})
        return

    conv_id_raw = raw.get("conversation_id")
    if not conv_id_raw:
        await websocket.send_json({"type": "error", "error": "conversation_id لازم است"})
        return
    try:
        conversation_id = uuid.UUID(str(conv_id_raw))
    except (ValueError, TypeError):
        await websocket.send_json({"type": "error", "error": "conversation_id نامعتبر است"})
        return

    if mtype == "message":
        content = str(raw.get("content", "")).strip()
        if not content or len(content) > 4000:
            await websocket.send_json({"type": "error", "error": "متن پیام نامعتبر است"})
            return
        reply_to_id = raw.get("reply_to_id")
        try:
            reply_uuid = uuid.UUID(str(reply_to_id)) if reply_to_id else None
        except (ValueError, TypeError):
            reply_uuid = None
        client_id = raw.get("client_id")

        async with SessionLocal() as db:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
            payload, member_ids = await chat_service.send_message(
                db, user, conversation_id, content, reply_uuid
            )
            payload["client_id"] = client_id

        await manager.broadcast_to_conversation(
            member_ids, {"type": "message.new", "message": payload}
        )
        await websocket.send_json(
            {"type": "message.sent", "client_id": client_id, "message": jsonable(payload)}
        )

    elif mtype == "typing":
        async with SessionLocal() as db:
            try:
                await chat_service.assert_member(db, conversation_id, user_id)
                ids = await chat_service._member_ids(db, conversation_id)
            except Exception:
                ids = None
        if ids:
            await manager.broadcast_to_conversation(
                {i for i in ids if i != user_id},
                {
                    "type": "typing",
                    "conversation_id": str(conversation_id),
                    "user_id": str(user_id),
                },
            )

    elif mtype == "read":
        async with SessionLocal() as db:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
            result = await chat_service.mark_read(db, user, conversation_id)
            member_ids = await chat_service._member_ids(db, conversation_id)
        await manager.broadcast_to_conversation(
            member_ids,
            {
                "type": "read",
                "conversation_id": str(conversation_id),
                "user_id": str(user_id),
                "last_read_at": result["last_read_at"].isoformat(),
            },
        )

    else:
        await websocket.send_json({"type": "error", "error": f"نوع پیام ناشناخته: {mtype}"})


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket, token: str = Query(default="")):
    user_id = await _auth(token)
    if not user_id:
        await websocket.close(code=4401, reason="invalid or expired token")
        return

    await manager.connect(user_id, websocket)
    try:
        await websocket.send_json({"type": "connected", "user_id": str(user_id)})
        while True:
            raw = await websocket.receive_json()
            try:
                await _run_frame(websocket, user_id, raw)
            except WebSocketDisconnect:
                raise
            except Exception:
                logger.exception("ws frame error (user=%s frame=%s)", user_id, raw.get("type"))
                try:
                    await websocket.send_json({"type": "error", "error": "خطای پردازش پیام"})
                except Exception:
                    pass

    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
    except Exception:
        logger.exception("ws connection fatal (user=%s)", user_id)
        manager.disconnect(user_id, websocket)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
