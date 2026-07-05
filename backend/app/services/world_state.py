"""Canonical world-state write helpers."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CANONICAL_WORLD_STATE, DEMO_SCENARIO_RUN_ID
from app.db.models import WorldStateCurrent, WorldStateSnapshot


def merge_state(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_state(merged[key], value)
        else:
            merged[key] = value
    return merged


async def read_world_state(session: AsyncSession) -> WorldStateCurrent | None:
    result = await session.execute(select(WorldStateCurrent).where(WorldStateCurrent.id.is_(True)))
    return result.scalar_one_or_none()


async def write_world_state(
    session: AsyncSession,
    state_patch: dict[str, Any],
    *,
    updated_by: str,
    reason: str,
) -> WorldStateCurrent:
    now = datetime.now(timezone.utc)
    current = await read_world_state(session)
    if current is None:
        current = WorldStateCurrent(
            id=True,
            scenario_run_id=DEMO_SCENARIO_RUN_ID,
            version=1,
            state=merge_state(CANONICAL_WORLD_STATE, state_patch),
            updated_by=updated_by,
            updated_at=now,
        )
        session.add(current)
        await session.flush()
    else:
        current.version += 1
        current.state = merge_state(current.state, state_patch)
        current.updated_by = updated_by
        current.updated_at = now

    session.add(
        WorldStateSnapshot(
            scenario_run_id=current.scenario_run_id,
            version=current.version,
            state=current.state,
            reason=reason,
            created_by=updated_by,
        )
    )
    return current
