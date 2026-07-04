"""Simulator control routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.agents.commander_agent import build_phase3_patch
from app.agents.power_orbit_agent import run_once as run_power_orbit_agent
from app.simulator.telemetry_generator import run_simulator_tick

router = APIRouter(tags=["simulator"])


@router.post("/simulator/scenario/{scenario_name}")
async def run_scenario_once(scenario_name: str) -> dict:
    event = await run_simulator_tick(0)
    finding = await run_power_orbit_agent()
    patch = await build_phase3_patch()
    return {
        "scenario": scenario_name,
        "telemetry_event": event["type"],
        "finding_id": finding.id if finding else None,
        "mission_patch_id": patch.id if patch else None,
        "mission_patch_status": patch.status if patch else None,
    }
