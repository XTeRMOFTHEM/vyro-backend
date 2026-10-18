"""VYRO — Tiny cache layer with Redis backend (if REDIS_URL set)
and an in-process TTL fallback (single-instance dev / no external deps).

Used for: frame catalog, trending hashtags, profile hot-reads, conversation membership.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

from app.core.config import settings


class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any:
        async with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            value, expires_at = item
            if expires_at and expires_at < time.monotonic():
                del self._data[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        async with self._lock:
            self._data[key] = (value, time.monotonic() + ttl if ttl else 0)

    async def delete(self, *keys: str) -> None:
        async with self._lock:
            for k in keys:
                self._data.pop(k, None)

    async def delete_prefix(self, prefix: str) -> None:
        async with self._lock:
            for k in [k for k in self._data if k.startswith(prefix)]:
                del self._data[k]


class RedisCache:
    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis  # lazy import

        self._redis = aioredis.from_url(url, encoding="utf-8", decode_responses=True)

    async def get(self, key: str) -> Any:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return raw

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        raw = json.dumps(value, ensure_ascii=False, default=str)
        if ttl:
            await self._redis.set(key, raw, ex=ttl)
        else:
            await self._redis.set(key, raw)

    async def delete(self, *keys: str) -> None:
        if keys:
            await self._redis.delete(*keys)

    async def delete_prefix(self, prefix: str) -> None:
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor=cursor, match=f"{prefix}*")
            if keys:
                await self._redis.delete(*keys)
            if cursor == 0:
                break


class Cache:
    """Facade — auto-selects backend."""

    def __init__(self) -> None:
        self._backend: MemoryCache | RedisCache | None = None
        self._initialized = False

    async def init(self) -> None:
        if self._initialized:
            return
        if settings.REDIS_URL:
            try:
                backend = RedisCache(settings.REDIS_URL)
                await backend._redis.ping()
                self._backend = backend
            except Exception:
                self._backend = MemoryCache()
        else:
            self._backend = MemoryCache()
        self._initialized = True

    @property
    def backend_name(self) -> str:
        return "redis" if isinstance(self._backend, RedisCache) else "memory"

    async def get(self, key: str) -> Any:
        await self.init()
        return await self._backend.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self.init()
        await self._backend.set(key, value, ttl)

    async def delete(self, *keys: str) -> None:
        await self.init()
        await self._backend.delete(*keys)

    async def delete_prefix(self, prefix: str) -> None:
        await self.init()
        await self._backend.delete_prefix(prefix)

    async def get_or_set(self, key: str, factory, ttl: int | None = None) -> Any:
        value = await self.get(key)
        if value is not None:
            return value
        value = await factory()
        if value is not None:
            await self.set(key, value, ttl)
        return value


cache = Cache()

# ---- standard key builders ----
KEY_FRAMES_CATALOG = "vyro:frames:catalog"
KEY_TRENDING_TAGS = "vyro:trending:hashtags"
KEY_PROFILE_PREFIX = "vyro:profile:"


def conv_members_key(conv_id: str) -> str:
    return f"vyro:conv:members:{conv_id}"
