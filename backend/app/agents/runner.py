"""Agent worker consuming simulator telemetry and running the Phase 3 vertical slice."""

from __future__ import annotations

import asyncio

from app.agents.commander_agent import build_phase3_patch
from app.agents.power_orbit_agent import run_once as run_power_orbit_once
from app.constants import StreamName
from app.services.bootstrap import wait_for_database_ready, wait_for_redis_ready
from app.services.redis_client import get_redis


async def ensure_group(stream: str, group: str) -> None:
    async with get_redis() as redis:
        try:
            await redis.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception as exc:  # noqa: BLE001
            if "BUSYGROUP" not in str(exc):
                raise


async def process_once() -> bool:
    async with get_redis() as redis:
        messages = await redis.xreadgroup(
            "agents",
            "orbitops-agents-1",
            {StreamName.telemetry_events.value: ">"},
            count=1,
            block=1000,
        )
        if not messages:
            return False
        stream_name, stream_messages = messages[0]
        message_id, _fields = stream_messages[0]

    finding = await run_power_orbit_once()
    if finding is not None:
        await build_phase3_patch()

    async with get_redis() as redis:
        await redis.xack(StreamName.telemetry_events.value, "agents", message_id)
    return True


async def run_forever() -> None:
    await wait_for_database_ready()
    await wait_for_redis_ready()
    await ensure_group(StreamName.telemetry_events.value, "agents")
    while True:
        processed = await process_once()
        if not processed:
            await asyncio.sleep(0.25)


if __name__ == "__main__":
    asyncio.run(run_forever())
