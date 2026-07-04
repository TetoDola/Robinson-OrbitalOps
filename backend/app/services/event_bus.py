"""Redis Stream publishing helpers."""

from __future__ import annotations

import json
from typing import Any

from app.services.redis_client import get_redis


async def publish_stream_event(stream_name: str, event: dict[str, Any]) -> str:
    async with get_redis() as redis:
        message_id = await redis.xadd(
            stream_name,
            {
                "type": event.get("type", ""),
                "payload": json.dumps(event, separators=(",", ":"), default=str),
            },
            maxlen=1000,
            approximate=True,
        )
    if isinstance(message_id, bytes):
        return message_id.decode("utf-8")
    return str(message_id)
