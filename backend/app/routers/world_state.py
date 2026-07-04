"""World-state routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WorldStateCurrent
from app.db.session import get_session
from app.schemas.world import WorldStateResponse

router = APIRouter()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@router.get("/world-state", response_model=WorldStateResponse, tags=["world-state"])
async def get_world_state(
    session: AsyncSession = Depends(get_session),
) -> WorldStateResponse:
    stmt = select(WorldStateCurrent).where(WorldStateCurrent.id.is_(True))
    result = await session.execute(stmt)
    world_state = result.scalar_one_or_none()
    if world_state is None:
        raise RuntimeError("World state is not seeded.")

    return WorldStateResponse(
        version=world_state.version,
        scenario_run_id=world_state.scenario_run_id,
        updated_by=world_state.updated_by,
        updated_at=_as_utc(world_state.updated_at),
        state=world_state.state,
    )
