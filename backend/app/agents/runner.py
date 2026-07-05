"""Agent worker consuming simulator telemetry and running the Phase 3 vertical slice."""

from __future__ import annotations

import asyncio
import time

from app.agents.data_context import read_current_agent_state
from app.agents.commander_agent import build_phase3_patch
from app.agents.domain_agents import emit_phase4_heartbeats_once, run_remaining_agents_once
from app.agents.power_orbit_agent import run_once as run_power_orbit_once
from app.constants import StreamName
from app.db.session import session_context
from app.services.agent_status import emit_agent_status
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

    await _emit_commander_dispatch()
    agent_state = await read_current_agent_state()
    finding = None
    remaining_findings = []
    if agent_state is not None:
        finding = await run_power_orbit_once(agent_state)
        remaining_findings = await run_remaining_agents_once(agent_state)
    if finding is not None or remaining_findings:
        await build_phase3_patch()

    async with get_redis() as redis:
        await redis.xack(StreamName.telemetry_events.value, "agents", message_id)
    return True


async def _emit_commander_dispatch() -> None:
    async with session_context() as session:
        await emit_agent_status(
            session,
            agent_name="commander_agent",
            status="dispatching",
            phase="dispatch",
            severity="INFO",
            message="Runtime change detected; dispatching domain agents.",
        )
        await session.commit()


async def run_forever() -> None:
    await wait_for_database_ready()
    await wait_for_redis_ready()
    await ensure_group(StreamName.telemetry_events.value, "agents")
    last_heartbeat = 0.0
    while True:
        now = time.monotonic()
        if now - last_heartbeat >= 10:
            await emit_phase4_heartbeats_once()
            last_heartbeat = now
        processed = await process_once()
        if not processed:
            await asyncio.sleep(0.25)


if __name__ == "__main__":
    asyncio.run(run_forever())
