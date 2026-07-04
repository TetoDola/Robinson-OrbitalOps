"""Demo reset helpers for repeatable hackathon runs."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants import AGENT_SEED_STATUS, DEMO_BASELINE_WORLD_STATE, DEMO_SCENARIO_NAME, DEMO_SCENARIO_RUN_ID, StreamName
from app.db.models import (
    AgentFinding,
    AgentStatus,
    AgentStatusEvent,
    Approval,
    Command,
    Incident,
    MissionPatch,
    OutboxEvent,
    ScenarioRun,
    TelemetryEvent,
    WorldStateCurrent,
    WorldStateSnapshot,
)
from app.services.event_bus import publish_stream_event


VOLATILE_RESET_MODELS = [
    OutboxEvent,
    Command,
    Approval,
    MissionPatch,
    Incident,
    AgentFinding,
    TelemetryEvent,
    AgentStatusEvent,
    WorldStateSnapshot,
]


async def reset_demo_database(session: AsyncSession) -> dict[str, Any]:
    """Reset Postgres-owned demo state without raw SQL or manual cleanup."""
    for model in VOLATILE_RESET_MODELS:
        await session.execute(delete(model))

    now = datetime.now(timezone.utc)
    scenario = await session.get(ScenarioRun, DEMO_SCENARIO_RUN_ID)
    if scenario is None:
        scenario = ScenarioRun(
            id=DEMO_SCENARIO_RUN_ID,
            scenario_name=DEMO_SCENARIO_NAME,
            status="running",
            metadata_={},
        )
        session.add(scenario)
    scenario.status = "running"
    scenario.metadata_ = {"source": "reset", "reset_at": now.isoformat(), "next_tick": 0}
    scenario.started_at = now
    scenario.ended_at = None

    state = deepcopy(DEMO_BASELINE_WORLD_STATE)
    world_result = await session.execute(select(WorldStateCurrent).where(WorldStateCurrent.id.is_(True)))
    world_state = world_result.scalar_one_or_none()
    if world_state is None:
        world_state = WorldStateCurrent(id=True)
        session.add(world_state)
    world_state.scenario_run_id = DEMO_SCENARIO_RUN_ID
    world_state.version = settings.world_state_seed_version
    world_state.state = state
    world_state.updated_by = "simulator-reset"
    world_state.updated_at = now

    session.add(
        WorldStateSnapshot(
            scenario_run_id=DEMO_SCENARIO_RUN_ID,
            version=settings.world_state_seed_version,
            state=state,
            reason="simulator_reset",
            created_by="simulator-reset",
            created_at=now,
        )
    )

    agents = []
    for seed_status in AGENT_SEED_STATUS:
        result = await session.execute(select(AgentStatus).where(AgentStatus.agent == seed_status["agent"]))
        row = result.scalar_one_or_none()
        if row is None:
            row = AgentStatus(agent=seed_status["agent"], display_name=seed_status["display_name"])
            session.add(row)
        row.display_name = seed_status["display_name"]
        row.status = seed_status["status"]
        row.phase = seed_status["phase"]
        row.severity = seed_status["severity"]
        row.message = seed_status["message"]
        row.linked_mission_patch_id = None
        row.updated_by = "simulator-reset"
        row.updated_at = now
        agent_payload = _agent_payload(row)
        agents.append(agent_payload)
        session.add(
            AgentStatusEvent(
                scenario_run_id=DEMO_SCENARIO_RUN_ID,
                agent_name=row.agent,
                display_name=row.display_name,
                status=row.status,
                phase=row.phase,
                severity=row.severity,
                message=row.message,
                affected_assets=[],
                metadata_={"source": "reset"},
                created_at=now,
            )
        )

    await session.commit()
    return reset_response_payload(state=state, agents=agents, reset_at=now)


def reset_response_payload(*, state: dict[str, Any], agents: list[dict[str, Any]], reset_at: datetime) -> dict[str, Any]:
    return {
        "scenario": DEMO_SCENARIO_NAME,
        "scenario_run_id": DEMO_SCENARIO_RUN_ID,
        "status": "running",
        "reset_at": reset_at.isoformat(),
        "world_state": {
            "version": settings.world_state_seed_version,
            "scenario_run_id": DEMO_SCENARIO_RUN_ID,
            "state": state,
        },
        "agents": agents,
        "cleared": [model.__tablename__ for model in VOLATILE_RESET_MODELS],
    }


async def publish_reset_baseline(payload: dict[str, Any]) -> None:
    timestamp = payload["reset_at"]
    await publish_stream_event(
        StreamName.ui_events.value,
        {
            "type": "simulator.reset",
            "timestamp": timestamp,
            "payload": {
                "scenario": payload["scenario"],
                "scenario_run_id": payload["scenario_run_id"],
                "status": payload["status"],
            },
        },
    )
    await publish_stream_event(
        StreamName.ui_events.value,
        {
            "type": "world_state.updated",
            "timestamp": timestamp,
            "payload": payload["world_state"],
        },
    )
    for agent in payload["agents"]:
        await publish_stream_event(
            StreamName.ui_events.value,
            {
                "type": "agent.status.updated",
                "timestamp": timestamp,
                "payload": agent,
            },
        )


def _agent_payload(row: AgentStatus) -> dict[str, Any]:
    return {
        "agent": row.agent,
        "display_name": row.display_name,
        "status": row.status,
        "phase": row.phase,
        "severity": row.severity,
        "message": row.message,
        "linked_mission_patch_id": row.linked_mission_patch_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
