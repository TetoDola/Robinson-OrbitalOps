"""Agent routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentStatus
from app.db.session import get_session
from app.schemas.agent import AgentsStatusResponse, AgentStatusItem

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
