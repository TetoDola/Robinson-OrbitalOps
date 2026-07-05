"""Shared data context builders for domain agents."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import session_context
from app.services.radiation_risk import get_radiation_risk_for_state
from app.services.world_state import read_world_state


RADIATION_CONTEXT_KEYS = (
    "radiationRiskScore",
    "radiationLevel",
    "mainCause",
    "recommendedAction",
    "explanation",
    "components",
    "inputs",
    "sourceMode",
    "sources",
    "generatedAt",
    "legacyRadiationRisk",
)


async def build_agent_world_state(session: AsyncSession) -> dict[str, Any] | None:
    """Read current mission state and attach compact computed data products."""
    world_state = await read_world_state(session)
    if world_state is None:
        return None
    return await enrich_agent_world_state(world_state.state)


async def read_current_agent_state() -> dict[str, Any] | None:
    async with session_context() as session:
        return await build_agent_world_state(session)


async def enrich_agent_world_state(
    state: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Return an agent-facing copy of world state with derived data attached."""
    enriched = deepcopy(state)
    radiation = enriched.setdefault("radiation", {})
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    try:
        risk = await get_radiation_risk_for_state(enriched, timestamp)
    except Exception as exc:  # noqa: BLE001 - agents should degrade, not crash, when ingest is down.
        radiation["computed_risk"] = {
            "available": False,
            "generatedAt": timestamp,
            "error": str(exc),
        }
        return enriched

    radiation["computed_risk"] = compact_radiation_risk(risk)
    return enriched


def compact_radiation_risk(risk: dict[str, Any]) -> dict[str, Any]:
    compact = {key: risk[key] for key in RADIATION_CONTEXT_KEYS if key in risk}
    compact["available"] = True
    return compact
