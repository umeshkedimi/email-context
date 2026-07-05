"""Thin async Redis cache with graceful degradation.

Every operation is best-effort: if Redis is unreachable or errors, we log and act
as a cache miss rather than failing the request. The cache is an optimization, not
a source of truth — Postgres remains authoritative.

Only non-plaintext data is ever cached here (the summary's *ciphertext* plus
metadata), so the at-rest encryption boundary holds even in the cache.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis
import structlog

from app.core.config import get_settings

log = structlog.get_logger("app.cache")

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Process-wide Redis client (lazy). decode_responses so we get str back."""
    global _client
    if _client is None:
        _client = aioredis.from_url(
            get_settings().redis_url, encoding="utf-8", decode_responses=True
        )
    return _client


async def cache_get_json(key: str) -> dict[str, Any] | None:
    try:
        raw = await get_redis().get(key)
    except Exception as exc:  # connection refused, timeout, etc.
        log.warning("cache_get_failed", key=key, error=str(exc))
        return None
    return json.loads(raw) if raw else None


async def cache_set_json(key: str, value: dict[str, Any], ttl_seconds: int) -> None:
    try:
        await get_redis().set(key, json.dumps(value), ex=ttl_seconds)
    except Exception as exc:
        log.warning("cache_set_failed", key=key, error=str(exc))


async def cache_delete(key: str) -> None:
    try:
        await get_redis().delete(key)
    except Exception as exc:
        log.warning("cache_delete_failed", key=key, error=str(exc))
