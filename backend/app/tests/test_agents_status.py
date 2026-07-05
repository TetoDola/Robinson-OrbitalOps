from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.routers.agents import list_agent_statuses
from app.schemas.agent import AgentsStatusResponse
from app.constants import AGENT_SEED_STATUS


class _Result:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarResult(self._values)


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _Session:
    async def execute(self, _statement):
        return _Result(
            [
                type(
                    "Status",
                    (),
                    {
                        "agent": seed["agent"],
                        "display_name": seed["display_name"],
                        "status": seed["status"],
                        "phase": seed["phase"],
                        "severity": seed["severity"],
                        "message": seed["message"],
                        "linked_mission_patch_id": None,
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
                for seed in AGENT_SEED_STATUS
            ]
        )


def test_agents_status_shape() -> None:
    response = asyncio.run(list_agent_statuses(_Session()))
    assert isinstance(response, AgentsStatusResponse)
    assert len(response.agents) == len(AGENT_SEED_STATUS)
    names = {agent.agent for agent in response.agents}
    expected = {seed["agent"] for seed in AGENT_SEED_STATUS}
    assert names == expected
