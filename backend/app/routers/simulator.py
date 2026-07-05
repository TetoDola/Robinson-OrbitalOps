"""Simulator control routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.agents.commander_agent import build_phase3_patch
from app.agents.domain_agents import run_remaining_agents_once
from app.agents.power_orbit_agent import run_once as run_power_orbit_agent
from app.constants import DEMO_SCENARIO_RUN_ID, StreamName
from app.db.models import ScenarioRun
from app.db.session import session_context
from app.schemas.simulator import SimulatorInjectRequest, SimulatorInjectResponse
from app.services.demo_reset import publish_reset_baseline, reset_demo_database
from app.services.event_bus import publish_stream_event
from app.services.manual_simulation import UnknownSimulatorIssueError, inject_named_issue
from app.simulator.telemetry_generator import run_simulator_tick

router = APIRouter(tags=["simulator"])


@router.post("/simulator/scenario/{scenario_name}")
async def run_scenario_once(scenario_name: str) -> dict:
    event = await run_simulator_tick(5)
    finding = await run_power_orbit_agent()
    remaining_findings = await run_remaining_agents_once()
    patch = await build_phase3_patch()
    return {
        "scenario": scenario_name,
        "telemetry_event": event["type"],
        "finding_id": finding.id if finding else None,
        "finding_count": (1 if finding else 0) + len(remaining_findings),
        "mission_patch_id": patch.id if patch else None,
        "mission_patch_status": patch.status if patch else None,
    }


@router.post("/simulator/reset")
async def reset_simulator() -> dict:
    async with session_context() as session:
        payload = await reset_demo_database(session)
    await publish_reset_baseline(payload)
    return payload


@router.post("/simulator/inject/{issue}", response_model=SimulatorInjectResponse)
async def inject_simulator_issue(issue: str, request: SimulatorInjectRequest | None = None) -> SimulatorInjectResponse:
    try:
        return await inject_named_issue(issue, request or SimulatorInjectRequest())
    except UnknownSimulatorIssueError as exc:
        # Only unknown issue names are 404s; other ValueErrors are real bugs and
        # must surface as 500s instead of masquerading as "not found".
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/simulator/pause")
async def pause_simulator() -> dict:
    return await _set_simulator_status("paused")


@router.post("/simulator/resume")
async def resume_simulator() -> dict:
    return await _set_simulator_status("running")


async def _set_simulator_status(status: str) -> dict:
    async with session_context() as session:
        scenario = await session.get(ScenarioRun, DEMO_SCENARIO_RUN_ID)
        if scenario is not None:
            scenario.status = status
            await session.commit()
    payload = {"scenario_run_id": DEMO_SCENARIO_RUN_ID, "status": status}
    await publish_stream_event(
        StreamName.ui_events.value,
        {
            "type": f"simulator.{status}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        },
    )
    return payload
