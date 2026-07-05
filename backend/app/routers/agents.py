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
AGENT_INTERVAL_SECONDS = 120
ACTIVE_AGENT_STATUSES = {"detecting", "analyzing", "explaining", "investigating", "planning", "proposing"}


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
            asset_id=request.asset_id,
            source=request.source,
            notes=request.notes,
        )
    )
    return ThermalImageInputResponse(
        image_id=response.image_id or "pending",
        asset_id=request.asset_id,
        analysis_status=response.analysis_status or "unknown",
        model_result=response.model_result,
        finding_id=response.finding_ids[0] if response.finding_ids else None,
        mission_patch_id=response.mission_patch_id,
        world_state_version=response.world_state_version,
    )


def _runtime_item(row: AgentStatus, now: datetime) -> AgentRuntimeItem:
    last_run_at = _as_utc(row.updated_at)
    next_run_at = last_run_at + timedelta(seconds=AGENT_INTERVAL_SECONDS)
    seconds_until = max(0, int((next_run_at - now).total_seconds()))
    age_seconds = max(0, int((now - last_run_at).total_seconds()))
    missed_runs = max(0, (age_seconds // AGENT_INTERVAL_SECONDS) - 1)
    if row.status in ACTIVE_AGENT_STATUSES:
        run_state = "running"
    elif missed_runs >= 2:
        run_state = "stale"
    elif missed_runs == 1:
        run_state = "missed"
    elif seconds_until == 0:
        run_state = "due"
    else:
        run_state = "scheduled"

    return AgentRuntimeItem(
        agent=row.agent,
        display_name=row.display_name,
        trigger_mode="interval",
        interval_seconds=AGENT_INTERVAL_SECONDS,
        run_state=run_state,
        last_run_at=last_run_at,
        next_run_at=next_run_at,
        seconds_until_next_run=seconds_until,
        missed_runs=missed_runs,
        last_result=row.message,
    )
