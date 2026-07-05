"""Agent routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentFinding, AgentStatus
from app.db.session import get_session
from app.schemas.agent import AgentFindingItem, AgentFindingsResponse, AgentsStatusResponse, AgentStatusItem

router = APIRouter()


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
