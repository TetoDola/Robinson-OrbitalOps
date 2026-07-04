"""Simulator worker that publishes deterministic orbital datacenter telemetry."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.constants import DEMO_SCENARIO_RUN_ID, StreamName
from app.db.models import TelemetryEvent
from app.db.session import session_context
from app.services.bootstrap import wait_for_database_ready, wait_for_redis_ready
from app.services.event_bus import publish_stream_event
from app.services.world_state import write_world_state
from app.simulator.scenarios import DEFAULT_TICK_SECONDS
from app.simulator.state_machine import build_simulated_state, build_telemetry_payload


async def run_simulator_tick(tick: int) -> dict:
    state = build_simulated_state(tick)
    payload = build_telemetry_payload(state)
    event = {
        "type": "telemetry.received",
        "event_type": "simulator.tick",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenario_run_id": DEMO_SCENARIO_RUN_ID,
        "asset_id": state["satellite"]["id"],
        "severity": "INFO",
        "payload": payload,
    }

    async with session_context() as session:
        world_state = await write_world_state(
            session,
            state,
            updated_by="orbitops-simulator",
            reason="simulator_tick",
        )
        session.add(
            TelemetryEvent(
                scenario_run_id=DEMO_SCENARIO_RUN_ID,
                event_type="simulator.tick",
                asset_id=state["satellite"]["id"],
                severity="INFO",
                payload=payload,
            )
        )
        await session.commit()
        event["world_state_version"] = world_state.version

    await publish_stream_event(StreamName.telemetry_events.value, event)
    await publish_stream_event(
        StreamName.ui_events.value,
        {
            "type": "world_state.updated",
            "timestamp": event["timestamp"],
            "payload": {
                "version": event["world_state_version"],
                "scenario_run_id": DEMO_SCENARIO_RUN_ID,
                "state": state,
            },
        },
    )
    return event


async def run_forever() -> None:
    await wait_for_database_ready()
    await wait_for_redis_ready()
    tick = 0
    while True:
        await run_simulator_tick(tick)
        tick += 1
        await asyncio.sleep(DEFAULT_TICK_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_forever())
