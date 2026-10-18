"""VYRO — Rate limiting (sliding-window in memory / fixed-window in Redis).

Usage in a route:
    @router.post("/login", dependencies=[Depends(auth_rate_limit)])
Custom key: rate_limit_by(times, seconds, key_builder=lambda request, user: ...)
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Awaitable, Callable

from fastapi import Request

from app.core.cache import cache
from app.core.config import settings
from app.core.errors import RateLimited

_rate_mem: dict[str, deque[float]] = defaultdict(deque)
_mem_lock = asyncio.Lock()


def _parse(spec: str) -> tuple[int, int]:
    try:
        times, seconds = spec.split("/")
        return int(times), int(seconds)
    except (ValueError, AttributeError):
        return 300, 60


async def _check_memory(key: str, times: int, seconds: int) -> bool:
    now = time.monotonic()
    async with _mem_lock:
        q = _rate_mem[key]
        while q and q[0] <= now - seconds:
            q.popleft()
        if len(q) >= times:
            return False
        q.append(now)
        # opportunistic cleanup
        if len(_rate_mem) > 10000:
            for k in [k for k, v in _rate_mem.items() if not v]:
                del _rate_mem[k]
        return True


async def _check_redis(key: str, times: int, seconds: int) -> bool:
    r = cache._backend._redis  # type: ignore[attr-defined]
    full_key = f"vyro:rl:{key}"
    count = await r.incr(full_key)
    if count == 1:
        await r.expire(full_key, seconds)
    return count <= times


async def check_rate(key: str, times: int, seconds: int) -> bool:
    from app.core.cache import cache as _cache

    await _cache.init()
    if _cache.backend_name == "redis":
        return await _check_redis(key, times, seconds)
    return await _check_memory(key, times, seconds)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(spec: str | None = None, scope: str = "ip"):
    """Dependency factory. scope: 'ip' or 'ip:path'."""

    async def _dep(request: Request) -> None:
        times, seconds = _parse(spec or settings.RATE_LIMIT_GLOBAL)
        key = client_ip(request)
        if scope == "ip:path":
            key = f"{key}:{request.url.path}"
        allowed = await check_rate(key, times, seconds)
        if not allowed:
            raise RateLimited()

    return _dep


def auth_rate_limit(spec: str | None = None):
    """Stricter limit for auth endpoints (per IP)."""

    async def _dep(request: Request) -> None:
        times, seconds = _parse(spec or settings.RATE_LIMIT_AUTH)
        key = f"auth:{client_ip(request)}:{request.url.path}"
        allowed = await check_rate(key, times, seconds)
        if not allowed:
            raise RateLimited()

    return _dep
