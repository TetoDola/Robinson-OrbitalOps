from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.routers.agents import list_agent_findings, list_agent_runtime, list_agent_statuses
from app.schemas.agent import AgentFindingsResponse, AgentsRuntimeResponse, AgentsStatusResponse
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


def test_agents_runtime_shape() -> None:
    response = asyncio.run(list_agent_runtime(_Session()))
    assert isinstance(response, AgentsRuntimeResponse)
    assert len(response.agents) == len(AGENT_SEED_STATUS)
    assert all(agent.interval_seconds == 120 for agent in response.agents)
    assert {agent.trigger_mode for agent in response.agents} == {"interval"}


class _FindingSession:
    async def execute(self, _statement):
        return _Result(
            [
                type(
                    "Finding",
                    (),
                    {
                        "id": "finding-1",
                        "agent_name": "thermal_physical_agent",
                        "severity": "RED",
                        "confidence": 0.9,
                        "affected_assets": ["node-c"],
                        "finding": "Node C hotspot is above safe thermal threshold.",
                        "evidence": ["Node C is hottest asset"],
                        "risk": "Node C should not receive critical workloads.",
                        "recommended_actions": ["mark_node_suspect"],
                        "status": "open",
                        "created_at": datetime.now(timezone.utc),
                    },
                )
            ]
        )


def test_agent_findings_shape() -> None:
    response = asyncio.run(list_agent_findings(session=_FindingSession()))

    assert isinstance(response, AgentFindingsResponse)
    assert len(response.findings) == 1
    assert response.findings[0].agent_name == "thermal_physical_agent"
    assert response.findings[0].confidence == 0.9
    assert response.findings[0].affected_assets == ["node-c"]
