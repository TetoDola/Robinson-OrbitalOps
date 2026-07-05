"""Simulator worker that publishes deterministic orbital datacenter telemetry."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.config import settings
from app.constants import DEMO_SCENARIO_NAME, DEMO_SCENARIO_RUN_ID, StreamName
from app.db.models import ScenarioRun, TelemetryEvent
from app.db.session import session_context
from app.services.bootstrap import wait_for_database_ready, wait_for_redis_ready
from app.services.event_bus import publish_stream_event
from app.services.local_gpu_telemetry import (
    build_local_gpu_event,
    gpu_world_state_patch,
    read_nvidia_smi_snapshot,
)
from app.services.world_state import write_world_state
from app.simulator.scenarios import DEFAULT_TICK_SECONDS
from app.simulator.state_machine import build_simulated_state, build_telemetry_payload


async def run_simulator_tick(tick: int) -> dict:
    state = build_simulated_state(tick)
    payload = build_telemetry_payload(state)
    local_snapshot = None
    if settings.local_gpu_telemetry_enabled:
        local_snapshot = await asyncio.to_thread(
            read_nvidia_smi_snapshot,
            node_id=settings.local_gpu_node_id,
            asset_id=settings.local_gpu_asset_id,
        )

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
        local_event: dict | None = None
        if local_snapshot is not None:
            world_state = await write_world_state(
                session,
                gpu_world_state_patch(local_snapshot),
                updated_by="orbitops-local-gpu",
                reason="local_gpu_telemetry",
            )
            local_event = build_local_gpu_event(
                local_snapshot,
                world_state_version=world_state.version,
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
        if local_event is not None:
            session.add(
                TelemetryEvent(
                    scenario_run_id=DEMO_SCENARIO_RUN_ID,
                    event_type="local_gpu.telemetry",
                    asset_id=local_snapshot["asset_id"] if local_snapshot else None,
                    severity="INFO",
                    payload=local_event["payload"],
                )
            )
        await session.commit()

    event["world_state_version"] = world_state.version

    await publish_stream_event(StreamName.telemetry_events.value, event)
    if local_event is not None:
        await publish_stream_event(StreamName.telemetry_events.value, local_event)
    await publish_stream_event(
        StreamName.ui_events.value,
        {
            "type": "world_state.updated",
            "timestamp": event["timestamp"],
            "payload": {
                "version": event["world_state_version"],
                "scenario_run_id": DEMO_SCENARIO_RUN_ID,
                "state": world_state.state,
            },
        },
    )
    if local_event is not None:
        await publish_stream_event(StreamName.ui_events.value, local_event)
    return event


async def claim_next_simulator_tick() -> int:
    async with session_context() as session:
        scenario = await session.get(ScenarioRun, DEMO_SCENARIO_RUN_ID)
        if scenario is None:
            scenario = ScenarioRun(
                id=DEMO_SCENARIO_RUN_ID,
                scenario_name=DEMO_SCENARIO_NAME,
                status="running",
                metadata_={"next_tick": 0},
            )
            session.add(scenario)
        tick = claim_next_tick_from_scenario(scenario)
        await session.commit()
        return tick


def claim_next_tick_from_scenario(scenario: ScenarioRun) -> int:
    metadata = dict(scenario.metadata_ or {})
    tick = int(metadata.get("next_tick", 0))
    metadata["next_tick"] = tick + 1
    scenario.metadata_ = metadata
    return tick


async def run_forever() -> None:
    await wait_for_database_ready()
    await wait_for_redis_ready()
    while True:
        tick = await claim_next_simulator_tick()
        await run_simulator_tick(tick)
        await asyncio.sleep(DEFAULT_TICK_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_forever())
