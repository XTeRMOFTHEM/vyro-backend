"""VYRO — WebSocket connection manager (single-instance now).

For multi-instance deployments, swap the fan-out with Redis pub/sub
(`PUBLISH vyro:ws` / subscriber task) — the interface below stays identical.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import WebSocket


def jsonable(obj):
    """Recursively convert non-JSON types (datetime/UUID/Decimal/...) to str."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(v) for v in obj]
    return str(obj)


class ConnectionManager:
    def __init__(self) -> None:
        self._sockets: dict[uuid.UUID, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    # ---------- lifecycle ----------
    async def connect(self, user_id: uuid.UUID, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._sockets.setdefault(user_id, set()).add(ws)

    def disconnect(self, user_id: uuid.UUID, ws: WebSocket) -> None:
        sockets = self._sockets.get(user_id)
        if sockets:
            sockets.discard(ws)
            if not sockets:
                self._sockets.pop(user_id, None)

    # ---------- presence ----------
    def is_online(self, user_id: uuid.UUID) -> bool:
        return bool(self._sockets.get(user_id))

    def online_count(self) -> int:
        return len(self._sockets)

    # ---------- sending ----------
    async def send_to_user(self, user_id: uuid.UUID, payload: dict) -> None:
        sockets = list(self._sockets.get(user_id, ()))
        if not sockets:
            return
        data = jsonable(payload)
        dead = []
        for ws in sockets:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

    async def broadcast_to_users(self, user_ids: set[uuid.UUID] | list[uuid.UUID], payload: dict) -> None:
        results = await asyncio.gather(
            *(self.send_to_user(uid, payload) for uid in set(user_ids)),
            return_exceptions=True,
        )
        _ = results  # errors swallowed inside send_to_user

    # broadcast to conversation participants (ids resolved by caller from DB)
    async def broadcast_to_conversation(
        self, member_ids: set[uuid.UUID] | list[uuid.UUID], payload: dict
    ) -> None:
        await self.broadcast_to_users(member_ids, payload)


manager = ConnectionManager()
