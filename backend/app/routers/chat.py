"""Operator chatbot routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AgentFinding,
    AgentStatus,
    AgentStatusEvent,
    Approval,
    Command,
    Incident,
    MissionPatch,
    ScenarioRun,
    TelemetryEvent,
    WorldStateCurrent,
    WorldStateSnapshot,
)
from app.db.session import get_session
from app.schemas.chat import ChatContextSummary, ChatTurn, OperatorChatRequest, OperatorChatResponse
from app.services.operator_chat import build_operator_chat_reply

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=OperatorChatResponse)
async def operator_chat(
    request: OperatorChatRequest,
    session: AsyncSession = Depends(get_session),
) -> OperatorChatResponse:
    world_state_result = await session.execute(select(WorldStateCurrent).where(WorldStateCurrent.id.is_(True)))
    scenario_runs_result = await session.execute(select(ScenarioRun).order_by(ScenarioRun.started_at.desc()).limit(5))
    agents_result = await session.execute(select(AgentStatus).order_by(AgentStatus.agent.asc()))
    agent_events_result = await session.execute(select(AgentStatusEvent).order_by(AgentStatusEvent.created_at.desc()).limit(25))
    findings_result = await session.execute(select(AgentFinding).order_by(AgentFinding.created_at.desc()).limit(25))
    incidents_result = await session.execute(select(Incident).order_by(Incident.updated_at.desc()).limit(25))
    mission_patches_result = await session.execute(select(MissionPatch).order_by(MissionPatch.created_at.desc()).limit(25))
    approvals_result = await session.execute(select(Approval).order_by(Approval.created_at.desc()).limit(25))
    commands_result = await session.execute(select(Command).order_by(Command.created_at.desc()).limit(25))
    telemetry_result = await session.execute(select(TelemetryEvent).order_by(TelemetryEvent.created_at.desc()).limit(25))
    snapshots_result = await session.execute(select(WorldStateSnapshot).order_by(WorldStateSnapshot.created_at.desc()).limit(5))
    patch_result = await session.execute(
        select(MissionPatch)
        .where(MissionPatch.status.in_(["pending_approval", "approved", "executing"]))
        .order_by(MissionPatch.created_at.desc())
    )

    reply = await build_operator_chat_reply(
        message=request.message.strip(),
        history=request.history,
        world_state=world_state_result.scalar_one_or_none(),
        scenario_runs=list(scenario_runs_result.scalars().all()),
        agents=list(agents_result.scalars().all()),
        agent_events=list(agent_events_result.scalars().all()),
        findings=list(findings_result.scalars().all()),
        incidents=list(incidents_result.scalars().all()),
        mission_patches=list(mission_patches_result.scalars().all()),
        approvals=list(approvals_result.scalars().all()),
        commands=list(commands_result.scalars().all()),
        telemetry_events=list(telemetry_result.scalars().all()),
        world_snapshots=list(snapshots_result.scalars().all()),
        mission_patch=patch_result.scalars().first(),
    )

    return OperatorChatResponse(
        message=ChatTurn(role="assistant", content=reply.content),
        source=reply.source,
        model=reply.model,
        context=ChatContextSummary(**reply.context_summary),
    )
