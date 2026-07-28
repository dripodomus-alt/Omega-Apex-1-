#!/usr/bin/env python3
# ==============================================================================
# redis_cache.py -- optional Redis acceleration for low-risk metadata.
#
# This cache is intentionally used for endpoint discovery and RPC validation, not
# live pool reserves or opportunity math. Stale pool state would create execution
# risk; stale endpoint metadata only costs a fallback retry.
# ==============================================================================

from __future__ import annotations

import logging
import json
import time
from typing import Any, Optional

from .config import (
    REDIS_ENABLED,
    REDIS_KEY_PREFIX,
    REDIS_RPC_CACHE_TTL_SECONDS,
    REDIS_URL,
)

logger = logging.getLogger(__name__)

_client = None
_connect_attempted = False


def enabled() -> bool:
    return REDIS_ENABLED.lower() in {"1", "true", "yes", "on"}


def client():
    """
    Returns a Redis client instance if enabled and available.
    Handles connection logic and failure gracefully.
    """
    global _client, _connect_attempted
    if not enabled():
        return None
    if _client is not None:
        return _client
    if _connect_attempted:
        return None

    _connect_attempted = True
    try:
        import redis
        candidate = redis.Redis.from_url(
            REDIS_URL,
            socket_connect_timeout=0.25,
            socket_timeout=0.5,
            decode_responses=True,
        )
        candidate.ping()
        _client = candidate
        return _client
    except Exception as e:
        # Log connection failure once to avoid spamming logs.
        logger.warning(f"Redis connection to {REDIS_URL} failed: {e}")
        return None


def key(*parts: object) -> str:
    """
    Constructs a Redis key with the project's standard prefix.
    """
    suffix = ":".join(str(part).strip(":") for part in parts)
    return f"{REDIS_KEY_PREFIX}:{suffix}"


def get_json(cache_key: str) -> Optional[Any]:
    c = client()
    if c is None:
        return None
    try:
        raw = c.get(cache_key)
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning(f"Redis get_json failed for key '{cache_key}': {e}")
        return None


def set_json(cache_key: str, value: Any, ttl: int = REDIS_RPC_CACHE_TTL_SECONDS) -> None:
    c = client()
    if c is None:
        return
    try:
        c.setex(cache_key, max(1, int(ttl)), json.dumps(value))
    except Exception as e:
        logger.warning(f"Redis set_json failed for key '{cache_key}': {e}")
        return


def hset_json(cache_key: str, field: str, value: Any, ttl: int | None = None) -> bool:
    c = client()
    if c is None:
        return False
    try:
        c.hset(cache_key, field, json.dumps(value, default=str))
        if ttl is not None:
            c.expire(cache_key, max(1, int(ttl)))
        return True
    except Exception as e:
        logger.warning(f"Redis hset_json failed for key '{cache_key}': {e}")
        return False


def hgetall_json(cache_key: str) -> dict[str, Any]:
    c = client()
    if c is None:
        return {}
    try:
        rows = c.hgetall(cache_key) or {}
        decoded: dict[str, Any] = {}
        for field, raw in rows.items():
            try:
                decoded[field] = json.loads(raw)
            except Exception:
                decoded[field] = raw
        return decoded
    except Exception as e:
        logger.warning(f"Redis hgetall_json failed for key '{cache_key}': {e}")
        return {}


def incr_with_ttl(cache_key: str, ttl: int) -> int | None:
    c = client()
    if c is None:
        return None
    try:
        pipe = c.pipeline()
        pipe.incr(cache_key)
        pipe.expire(cache_key, max(1, int(ttl)))
        value, _ = pipe.execute()
        return int(value)
    except Exception as e:
        logger.warning(f"Redis incr_with_ttl failed for key '{cache_key}': {e}")
        return None


def xadd(stream: str, fields: dict[str, Any], maxlen: int = 10000) -> str:
    c = client()
    if c is None:
        return ""
    try:
        payload = {
            str(k): json.dumps(v, default=str) if isinstance(v, (dict, list, tuple)) else str(v)
            for k, v in fields.items()
        }
        payload.setdefault("ts", str(time.time()))
        return str(c.xadd(stream, payload, maxlen=max(1, int(maxlen)), approximate=True))
    except Exception as e:
        logger.warning(f"Redis xadd failed for stream '{stream}': {e}")
        return ""


def xread(streams: dict[str, str], count: int | None = None, block: int | None = None) -> list[tuple[str, list[tuple[str, dict[str, str]]]]] | None:
    c = client()
    if c is None:
        return None
    try:
        # redis-py xread returns a list of streams, where each stream is a tuple of (stream_name, list_of_messages)
        # e.g., [('mystream', [('1625078891832-0', {'field1': 'value1'})])]
        response = c.xread(streams, count=count, block=block)
        if not response:
            return None

        # The redis client with decode_responses=True should handle decoding keys and values.
        # The result from redis-py is already in the desired format.
        return response
    except Exception as e:
        logger.warning(f"Redis xread failed for streams '{streams.keys()}': {e}")
        return None

def status() -> tuple[bool, str]:
    if not enabled():
        return False, "disabled"
    c = client()
    if c is None:
        return False, "unavailable"
    try:
        pong = c.ping()
        return bool(pong), "connected" if pong else "ping_failed"
    except Exception as exc:
        return False, type(exc).__name__


def delete_by_pattern(pattern: str) -> int:
    """
    Deletes keys matching a given pattern. Use with caution.
    Aligns with data governance for explicit data removal.
    """
    c = client()
    if c is None:
        return 0
    keys_to_delete = [key for key in c.scan_iter(match=pattern)]
    if not keys_to_delete:
        return 0
    return c.delete(*keys_to_delete)
