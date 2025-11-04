"""Feature payload caching helpers.

Provides a best-effort cache for the last successful `/v1/features/today`
payload per user. Redis is preferred when configured via `REDIS_URL`; an
in-memory LRU cache is used as a fallback so we can still serve data when the
database is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

from .db import settings

try:  # pragma: no cover - exercised in environments with Redis available
    from redis.asyncio import Redis  # type: ignore
    from redis.exceptions import RedisError  # type: ignore
except Exception:  # pragma: no cover - redis package may be optional
    Redis = None  # type: ignore[assignment]
    RedisError = Exception  # type: ignore[assignment]


logger = logging.getLogger(__name__)

_CACHE_KEY_PREFIX = "features_last_good:"
_DEFAULT_CACHE_TTL_SECONDS = 6 * 60 * 60


class _LRUCache:
    """Simple LRU cache with TTL semantics for async contexts."""

    def __init__(self, maxsize: int = 256) -> None:
        self.maxsize = maxsize
        self._data: "OrderedDict[str, tuple[float, Dict[str, Any]]]" = OrderedDict()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        item = self._data.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._data.pop(key, None)
            return None
        # Refresh position for LRU
        self._data.move_to_end(key, last=True)
        return value

    def set(self, key: str, value: Dict[str, Any], ttl: int) -> None:
        expires_at = time.time() + ttl
        if key in self._data:
            self._data.pop(key)
        elif len(self._data) >= self.maxsize:
            self._data.popitem(last=False)
        self._data[key] = (expires_at, value)


_redis_client: Optional["Redis"] = None
_redis_lock = asyncio.Lock()
_redis_attempted = False


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # pragma: no cover - defensive fallback
            return str(value)
    return value


async def _get_redis_client() -> Optional["Redis"]:
    global _redis_client, _redis_attempted
    if Redis is None:
        return None
    if _redis_client is not None:
        return _redis_client
    if _redis_attempted:
        return None

    async with _redis_lock:
        if _redis_client is not None:
            return _redis_client
        if _redis_attempted:
            return None
        _redis_attempted = True

        url = getattr(settings, "REDIS_URL", None)
        if not url:
            return None

        try:
            client = Redis.from_url(url)
        except Exception as exc:  # pragma: no cover - connection constructor failure
            logger.warning("[CACHE] failed to create redis client: %s", exc)
            return None

        try:
            await client.ping()
        except Exception as exc:  # pragma: no cover - connection failure
            logger.warning("[CACHE] redis ping failed: %s", exc)
            return None

        _redis_client = client
        logger.info("[CACHE] redis backend enabled")
        return _redis_client


class FeatureCache:
    def __init__(self, ttl: int = _DEFAULT_CACHE_TTL_SECONDS, maxsize: int = 512) -> None:
        self.ttl = ttl
        self._memory_cache = _LRUCache(maxsize=maxsize)
        self._memory_lock = asyncio.Lock()

    async def get(self, user_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not user_id:
            return None
        key = f"{_CACHE_KEY_PREFIX}{user_id}"

        client = await _get_redis_client()
        if client is not None:
            try:
                raw = await client.get(key)
            except RedisError as exc:  # pragma: no cover - network failure
                logger.warning("[CACHE] redis get failed: %s", exc)
            else:
                if raw:
                    try:
                        return json.loads(raw)
                    except json.JSONDecodeError:  # pragma: no cover - corrupted entry
                        logger.warning("[CACHE] redis payload corrupted for %s", key)

        async with self._memory_lock:
            return self._memory_cache.get(key)

    async def set(self, user_id: Optional[str], payload: Dict[str, Any]) -> None:
        if not user_id:
            return

        key = f"{_CACHE_KEY_PREFIX}{user_id}"
        safe_payload = json.loads(json.dumps(payload, default=_json_default))

        client = await _get_redis_client()
        if client is not None:
            try:
                await client.set(key, json.dumps(safe_payload), ex=self.ttl)
            except RedisError as exc:  # pragma: no cover - network failure
                logger.warning("[CACHE] redis set failed: %s", exc)

        async with self._memory_lock:
            self._memory_cache.set(key, safe_payload, self.ttl)

        logger.info("[CACHE] updated features:%s", user_id)


_feature_cache = FeatureCache()


async def get_last_good(user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    return await _feature_cache.get(user_id)


async def set_last_good(user_id: Optional[str], payload: Dict[str, Any]) -> None:
    await _feature_cache.set(user_id, payload)
