from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.db.models import WorldStateCurrent
from app.routers.world_state import get_world_state
from app.schemas.world import WorldStateResponse
from app.constants import CANONICAL_WORLD_STATE


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _Session:
    async def execute(self, _statement):
        return _Result(
            WorldStateCurrent(
                id=True,
                scenario_run_id="phase-1-run",
                version=1,
                state=CANONICAL_WORLD_STATE,
                updated_by="seed",
                updated_at=datetime.now(timezone.utc),
            )
        )


def test_world_state_shape() -> None:
    response = asyncio.run(get_world_state(_Session()))
    assert isinstance(response, WorldStateResponse)
    assert response.version == 1
    assert response.scenario_run_id == "phase-1-run"
    assert response.state["scenario"] == CANONICAL_WORLD_STATE["scenario"]
    assert response.updated_by == "seed"
