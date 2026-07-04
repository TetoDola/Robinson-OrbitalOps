"""Redis connection utilities."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from app.config import settings


_client: Redis | None = None


@asynccontextmanager
async def get_redis() -> AsyncIterator[Redis]:
    global _client
    if _client is None:
        _client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=settings.redis_connect_timeout_seconds,
            socket_timeout=settings.redis_connect_timeout_seconds,
            retry_on_error=[ConnectionError],
        )

    try:
        yield _client
    finally:
        # Re-use across requests while app is alive.
        pass


async def ping_redis() -> bool:
    attempts = settings.redis_retry_attempts
    delay = settings.redis_retry_delay_seconds

    async with get_redis() as redis:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                await redis.ping()
                return True
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                await asyncio.sleep(delay)

        if last_error is not None:
            raise last_error
        return False


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
