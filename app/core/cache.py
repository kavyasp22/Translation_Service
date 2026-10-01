"""
Thin async Redis wrapper. If Redis is down or disabled, every call becomes a no-op
so the translation pipeline keeps working (just without caching) instead of crashing.
"""
import hashlib
import json
import logging
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import get_settings

logger = logging.getLogger("translation_service.cache")


def make_cache_key(text: str, source_lang: str, target_lang: str) -> str:
    raw = f"{source_lang}:{target_lang}:{text}".encode("utf-8")
    return "translate:" + hashlib.sha256(raw).hexdigest()


def make_chunk_cache_key(text: str, source_lang: str, target_lang: str) -> str:
    """Separate namespace from make_cache_key(), used for individually-cached
    Gemma chunks (see app/models/gemma_model.py) rather than whole documents.
    Confirmed real case this helps: recurring boilerplate (e.g. a Telegram
    channel's identical post intro/tagline reused across many otherwise-
    unique posts) becomes a cache hit after the first time, instead of every
    document needing a fresh Gemma call purely because the DOCUMENT as a
    whole is unique even when large pieces of it are not."""
    raw = f"{source_lang}:{target_lang}:{text}".encode("utf-8")
    return "gemma_chunk:" + hashlib.sha256(raw).hexdigest()


class TranslationCache:
    def __init__(self):
        self._settings = get_settings()
        self._client: Optional[aioredis.Redis] = None

    async def connect(self):
        if not self._settings.cache_enabled:
            return
        try:
            self._client = aioredis.from_url(
                self._settings.redis_url, decode_responses=True
            )
            await self._client.ping()
            logger.info("Connected to Redis cache")
        except Exception as e:
            logger.warning(f"Redis unavailable, caching disabled: {e}")
            self._client = None

    async def get(self, key: str) -> Optional[dict]:
        if not self._client:
            return None
        try:
            raw = await self._client.get(key)
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
            return None

    async def set(self, key: str, value: dict):
        if not self._client:
            return
        try:
            await self._client.set(
                key, json.dumps(value), ex=self._settings.cache_ttl_seconds
            )
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")

    async def close(self):
        if self._client:
            await self._client.close()


cache = TranslationCache()
