"""Idempotent seed helpers for Phase 1 state."""

from __future__ import annotations

import datetime as dt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants import AGENT_SEED_STATUS, CANONICAL_WORLD_STATE

from .models import AgentStatus, WorldStateCurrent


async def _upsert_world_state(session: AsyncSession) -> None:
    result = await session.execute(select(WorldStateCurrent).where(WorldStateCurrent.id.is_(True)))
    world_state = result.scalar_one_or_none()

    if world_state is None:
        session.add(
            WorldStateCurrent(
                id=True,
                scenario_run_id="phase-1-run",
                version=settings.world_state_seed_version,
                state=CANONICAL_WORLD_STATE,
                updated_by="seed",
            )
        )


async def _upsert_agent_statuses(session: AsyncSession) -> None:
    for status in AGENT_SEED_STATUS:
        stmt = select(AgentStatus).where(AgentStatus.agent == status["agent"])
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is None:
            now = dt.datetime.now(dt.timezone.utc)
            session.add(
                AgentStatus(
                    agent=status["agent"],
                    display_name=status["display_name"],
                    status=status["status"],
                    phase=status["phase"],
                    severity=status["severity"],
                    message=status["message"],
                    updated_by="seed",
                    updated_at=now,
                )
            )


async def seed_initial_data(session: AsyncSession) -> None:
    await _upsert_world_state(session)
    await _upsert_agent_statuses(session)
    await session.commit()
