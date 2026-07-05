"""Agent routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentFinding, AgentStatus
from app.db.session import get_session
from app.config import settings
from app.schemas.agent import (
    AiStatusResponse,
    AgentFindingItem,
    AgentFindingsResponse,
    AgentRuntimeItem,
    AgentsRuntimeResponse,
    AgentsStatusResponse,
    AgentStatusItem,
    ThermalImageInputRequest,
    ThermalImageInputResponse,
)
from app.schemas.simulator import SimulatorInjectRequest
from app.services.manual_simulation import inject_thermal_frame

router = APIRouter()
AGENT_HEARTBEAT_SECONDS = 10
ACTIVE_AGENT_STATUSES = {
    "detecting",
    "analyzing",
    "dispatching",
    "explaining",
    "investigating",
    "planning",
    "proposing",
}
APPROVAL_AGENT_STATUSES = {"awaiting_approval"}
COMMANDER_AGENT_NAME = "commander_agent"
AGENT_RUNTIME_METADATA = {
    "workload_agent": {
        "trigger_condition": "Commander dispatches this agent when GPU utilization, rank lag, or training state changes.",
        "watched_fields": ["nodes[].gpu_util", "nodes[].rank_lag", "training.status"],
    },
    "thermal_physical_agent": {
        "trigger_condition": "Commander dispatches this agent when temperature, hotspot, cooling, visual input, or vibration changes.",
        "watched_fields": [
            "thermal.highest_temp_c",
            "thermal.hotspot_node",
            "thermal.cooling_status",
            "thermal.latest_visual_input",
            "nodes[].temp_c",
            "nodes[].vibration_score",
        ],
    },
    "power_orbit_agent": {
        "trigger_condition": "Commander dispatches this agent when battery, solar, eclipse countdown, or checkpoint freshness changes.",
        "watched_fields": [
            "power.battery_percent",
            "power.solar_kw",
            "satellite.time_to_eclipse_min",
            "training.latest_checkpoint_status",
        ],
    },
    "radiation_integrity_agent": {
        "trigger_condition": "Commander dispatches this agent when radiation, ECC, Xid, loss-state, or checkpoint trust changes.",
        "watched_fields": [
            "radiation.ecc_errors_last_5min",
            "radiation.xid_event",
            "radiation.computed_risk",
            "training.loss_state",
            "training.latest_checkpoint_status",
        ],
    },
    "checkpoint_downlink_agent": {
        "trigger_condition": "Commander dispatches this agent when checkpoint, downlink capacity, or contact-window changes.",
        "watched_fields": [
            "downlink.capacity_gb",
            "downlink.used_gb",
            "downlink.window_open",
            "training.latest_checkpoint",
        ],
    },
    "vibration_health_agent": {
        "trigger_condition": "Commander dispatches this agent when vibration, cooling, or hotspot correlation changes.",
        "watched_fields": ["nodes[].vibration_score", "thermal.cooling_status", "thermal.highest_temp_c"],
    },
    COMMANDER_AGENT_NAME: {
        "trigger_condition": "Commander watches runtime changes, dispatches domain agents, and groups returned findings.",
        "watched_fields": ["agent_findings.status", "mission_patches.status", "incidents.status"],
    },
}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@router.get("/agents/status", response_model=AgentsStatusResponse, tags=["agents"])
async def list_agent_statuses(
    session: AsyncSession = Depends(get_session),
) -> AgentsStatusResponse:
    result = await session.execute(select(AgentStatus).order_by(AgentStatus.agent.asc()))
    agent_rows = result.scalars().all()

    return AgentsStatusResponse(
        agents=[
            AgentStatusItem(
                agent=row.agent,
                display_name=row.display_name,
                status=row.status,
                phase=row.phase,
                severity=row.severity,
                message=row.message,
                linked_mission_patch_id=row.linked_mission_patch_id,
                updated_at=_as_utc(row.updated_at),
            )
            for row in agent_rows
        ]
    )


@router.get("/agents/ai-status", response_model=AiStatusResponse, tags=["agents"])
async def get_ai_status() -> AiStatusResponse:
    configured = bool(settings.crusoe_api_key)
    enabled = bool(settings.crusoe_enabled)
    connected = bool(enabled and configured)
    return AiStatusResponse(
        provider="crusoe",
        enabled=enabled,
        configured=configured,
        connected=connected,
        status="connected" if connected else "missing_api_key" if enabled and not configured else "disabled_by_flag",
        text_model=settings.crusoe_model,
        multimodal_model=settings.crusoe_multimodal_model,
    )


@router.get("/agents/runtime", response_model=AgentsRuntimeResponse, tags=["agents"])
async def list_agent_runtime(
    session: AsyncSession = Depends(get_session),
) -> AgentsRuntimeResponse:
    result = await session.execute(select(AgentStatus).order_by(AgentStatus.agent.asc()))
    agent_rows = result.scalars().all()
    now = datetime.now(timezone.utc)
    return AgentsRuntimeResponse(agents=[_runtime_item(row, now) for row in agent_rows])


@router.get("/agents/findings", response_model=AgentFindingsResponse, tags=["agents"])
async def list_agent_findings(
    agent: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    session: AsyncSession = Depends(get_session),
) -> AgentFindingsResponse:
    stmt = select(AgentFinding)
    if agent:
        stmt = stmt.where(AgentFinding.agent_name == agent)
    stmt = stmt.order_by(AgentFinding.created_at.desc()).limit(limit)

    result = await session.execute(stmt)
    finding_rows = result.scalars().all()

    return AgentFindingsResponse(
        findings=[
            AgentFindingItem(
                id=row.id,
                agent_name=row.agent_name,
                severity=row.severity,
                confidence=float(row.confidence),
                affected_assets=row.affected_assets,
                finding=row.finding,
                evidence=row.evidence,
                risk=row.risk,
                recommended_actions=row.recommended_actions,
                status=row.status,
                created_at=_as_utc(row.created_at),
            )
            for row in finding_rows
        ]
    )


@router.post("/agents/thermal/input-image", response_model=ThermalImageInputResponse, tags=["agents"])
async def submit_thermal_image(request: ThermalImageInputRequest) -> ThermalImageInputResponse:
    response = await inject_thermal_frame(
        SimulatorInjectRequest(
            image_data_url=request.image_data_url,
            audio_data_url=request.audio_data_url,
            audio_mime_type=request.audio_mime_type,
            audio_duration_s=request.audio_duration_s,
            audio_notes=request.audio_notes,
            asset_id=request.asset_id,
            source=request.source,
            notes=request.notes,
        )
    )
    return ThermalImageInputResponse(
        image_id=response.image_id or "pending",
        audio_id=response.audio_id,
        asset_id=request.asset_id,
        analysis_status=response.analysis_status or "unknown",
        model_result=response.model_result,
        finding_id=response.finding_ids[0] if response.finding_ids else None,
        mission_patch_id=response.mission_patch_id,
        world_state_version=response.world_state_version,
    )


def _runtime_item(row: AgentStatus, now: datetime) -> AgentRuntimeItem:
    last_run_at = _as_utc(row.updated_at)
    next_run_at = last_run_at + timedelta(seconds=AGENT_HEARTBEAT_SECONDS)
    seconds_until = max(0, int((next_run_at - now).total_seconds()))
    age_seconds = max(0, int((now - last_run_at).total_seconds()))
    missed_runs = max(0, (age_seconds // AGENT_HEARTBEAT_SECONDS) - 1)
    trigger_mode = "finding_event" if row.agent == COMMANDER_AGENT_NAME else "runtime_change"
    metadata = AGENT_RUNTIME_METADATA.get(
        row.agent,
        {"trigger_condition": "Runtime state changes.", "watched_fields": []},
    )
    if row.status in APPROVAL_AGENT_STATUSES:
        run_state = "awaiting_approval"
        last_triggered_by = "mission_patch"
    elif row.status in ACTIVE_AGENT_STATUSES:
        run_state = "running"
        last_triggered_by = "commander_dispatch" if row.agent != COMMANDER_AGENT_NAME else trigger_mode
    elif missed_runs >= 6:
        run_state = "stale"
        last_triggered_by = "heartbeat"
    elif row.agent == COMMANDER_AGENT_NAME:
        run_state = "awaiting_findings"
        last_triggered_by = "finding_event"
    else:
        run_state = "watching"
        last_triggered_by = "heartbeat"

    return AgentRuntimeItem(
        agent=row.agent,
        display_name=row.display_name,
        trigger_mode=trigger_mode,
        trigger_condition=metadata["trigger_condition"],
        watched_fields=metadata["watched_fields"],
        interval_seconds=AGENT_HEARTBEAT_SECONDS,
        heartbeat_seconds=AGENT_HEARTBEAT_SECONDS,
        run_state=run_state,
        last_run_at=last_run_at,
        next_run_at=next_run_at,
        seconds_until_next_run=seconds_until,
        missed_runs=missed_runs,
        last_triggered_by=last_triggered_by,
        last_result=row.message,
    )
