from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.constants import AGENT_SEED_STATUS, CANONICAL_WORLD_STATE, DEMO_BASELINE_WORLD_STATE, DEMO_SCENARIO_NAME, DEMO_SCENARIO_RUN_ID
from app.db.models import (
    AgentFinding,
    AgentStatus,
    AgentStatusEvent,
    Approval,
    Command,
    Incident,
    MissionPatch,
    OutboxEvent,
    ScenarioRun,
    TelemetryEvent,
    WorldStateCurrent,
    WorldStateSnapshot,
)
from app.routers import simulator
from app.services.demo_reset import VOLATILE_RESET_MODELS, publish_reset_baseline, reset_demo_database, reset_response_payload
from app.simulator.telemetry_generator import claim_next_tick_from_scenario


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        if isinstance(self.value, list):
            return self.value[0] if self.value else None
        return self.value


class _FakeResetSession:
    def __init__(self):
        self.rows = _seed_rows()
        self.commits = 0

    async def execute(self, statement):
        if getattr(statement, "is_delete", False):
            model = _MODEL_BY_TABLE[statement.table.name]
            self.rows[model] = []
            return _Result(None)

        entity = statement.column_descriptions[0]["entity"]
        if entity is WorldStateCurrent:
            return _Result(self.rows[WorldStateCurrent])
        if entity is AgentStatus:
            params = statement.compile().params
            agent = next((value for key, value in params.items() if key.startswith("agent")), None)
            return _Result([row for row in self.rows[AgentStatus] if row.agent == agent])
        return _Result([])

    async def get(self, model, key):
        if model is ScenarioRun:
            return next((row for row in self.rows[ScenarioRun] if row.id == key), None)
        return None

    def add(self, row):
        self.rows.setdefault(type(row), []).append(row)

    async def commit(self):
        self.commits += 1


def test_reset_clears_all_repeat_demo_volatile_tables() -> None:
    table_names = [model.__tablename__ for model in VOLATILE_RESET_MODELS]

    assert table_names == [
        "outbox_events",
        "commands",
        "approvals",
        "mission_patches",
        "incidents",
        "agent_findings",
        "telemetry_events",
        "agent_status_events",
        "world_state_snapshots",
    ]


def test_reset_response_is_frontend_friendly_baseline() -> None:
    reset_at = datetime.now(timezone.utc)
    agents = [
        {
            "agent": item["agent"],
            "display_name": item["display_name"],
            "status": item["status"],
            "phase": item["phase"],
            "severity": item["severity"],
            "message": item["message"],
            "linked_mission_patch_id": None,
            "updated_at": reset_at.isoformat(),
        }
        for item in AGENT_SEED_STATUS
    ]

    payload = reset_response_payload(state=DEMO_BASELINE_WORLD_STATE, agents=agents, reset_at=reset_at)

    assert payload["scenario"] == DEMO_SCENARIO_NAME
    assert payload["scenario_run_id"] == DEMO_SCENARIO_RUN_ID
    assert payload["status"] == "paused"
    assert payload["world_state"]["state"]["tick"] == 0
    assert payload["world_state"]["state"]["active_mission_patch"] is None
    assert len(payload["agents"]) == len(AGENT_SEED_STATUS)
    assert "mission_patches" in payload["cleared"]


def test_reset_demo_database_clears_stale_rows_and_restores_baseline() -> None:
    session = _FakeResetSession()

    payload = asyncio.run(reset_demo_database(session))

    assert session.commits == 1
    assert session.rows[Command] == []
    assert session.rows[Approval] == []
    assert session.rows[MissionPatch] == []
    assert session.rows[Incident] == []
    assert session.rows[AgentFinding] == []
    assert session.rows[TelemetryEvent] == []
    assert session.rows[OutboxEvent] == []
    assert len(session.rows[WorldStateSnapshot]) == 1
    assert len(session.rows[AgentStatusEvent]) == len(AGENT_SEED_STATUS)

    world_state = session.rows[WorldStateCurrent][0]
    assert world_state.state == DEMO_BASELINE_WORLD_STATE
    assert world_state.state["tick"] == 0
    assert world_state.state["power"]["battery_percent"] == 62
    assert world_state.state["training"]["latest_checkpoint_status"] == "trusted"
    assert world_state.state["active_mission_patch"] is None

    scenario = session.rows[ScenarioRun][0]
    assert scenario.status == "paused"
    assert scenario.ended_at is None
    assert scenario.metadata_["next_tick"] == 0
    assert all(row.status in {"monitoring", "healthy"} for row in session.rows[AgentStatus])
    assert payload["world_state"]["state"] == DEMO_BASELINE_WORLD_STATE


def test_simulator_tick_claim_uses_scenario_metadata() -> None:
    scenario = ScenarioRun(
        id=DEMO_SCENARIO_RUN_ID,
        scenario_name=DEMO_SCENARIO_NAME,
        status="running",
        metadata_={"next_tick": 0},
    )

    assert claim_next_tick_from_scenario(scenario) == 0
    assert scenario.metadata_["next_tick"] == 1
    assert claim_next_tick_from_scenario(scenario) == 1
    assert scenario.metadata_["next_tick"] == 2


def test_publish_reset_baseline_emits_frontend_reconnect_events(monkeypatch) -> None:
    reset_at = datetime.now(timezone.utc)
    payload = reset_response_payload(
        state=DEMO_BASELINE_WORLD_STATE,
        agents=[
            {
                "agent": item["agent"],
                "display_name": item["display_name"],
                "status": item["status"],
                "phase": item["phase"],
                "severity": item["severity"],
                "message": item["message"],
                "linked_mission_patch_id": None,
                "updated_at": reset_at.isoformat(),
            }
            for item in AGENT_SEED_STATUS
        ],
        reset_at=reset_at,
    )
    events = []

    async def fake_publish(stream, event):
        events.append({"stream": stream, "event": event})

    monkeypatch.setattr("app.services.demo_reset.publish_stream_event", fake_publish)

    asyncio.run(publish_reset_baseline(payload))

    assert events[0]["event"]["type"] == "simulator.reset"
    assert events[1]["event"]["type"] == "world_state.updated"
    assert [event["event"]["type"] for event in events[2:]] == ["agent.status.updated"] * len(AGENT_SEED_STATUS)


def test_simulator_routes_expose_reset_pause_resume_and_all_agent_scenario() -> None:
    routes = {route.path for route in simulator.router.routes}

    assert "/simulator/reset" in routes
    assert "/simulator/pause" in routes
    assert "/simulator/resume" in routes
    assert "/simulator/inject/{issue}" in routes
    assert "/simulator/scenario/{scenario_name}" in routes
    assert "run_remaining_agents_once" in simulator.run_scenario_once.__code__.co_names


def _seed_rows() -> dict:
    return {
        ScenarioRun: [
            ScenarioRun(
                id=DEMO_SCENARIO_RUN_ID,
                scenario_name=DEMO_SCENARIO_NAME,
                status="completed",
                metadata_={"source": "test"},
                ended_at=datetime.now(timezone.utc),
            )
        ],
        WorldStateCurrent: [
            WorldStateCurrent(
                id=True,
                scenario_run_id=DEMO_SCENARIO_RUN_ID,
                version=99,
                state=CANONICAL_WORLD_STATE,
                updated_by="test",
            )
        ],
        AgentStatus: [
            AgentStatus(
                agent=item["agent"],
                display_name=item["display_name"],
                status="stale",
                phase="verify",
                severity="RED",
                message="stale state",
                updated_by="test",
            )
            for item in AGENT_SEED_STATUS
        ],
        OutboxEvent: [OutboxEvent(stream="ui:events", event_type="stale", payload={}, status="pending", idempotency_key="outbox-stale")],
        Command: [
            Command(
                mission_patch_id="patch-stale",
                action_type="run_health_check",
                status="queued",
                input={},
                result={},
                idempotency_key="command-stale",
            )
        ],
        Approval: [Approval(mission_patch_id="patch-stale", status="approved", idempotency_key="approval-stale")],
        MissionPatch: [
            MissionPatch(
                id="patch-stale",
                severity="RED",
                status="verified",
                summary="stale",
                evidence=[],
                actions=[],
                rollback_plan={},
                approval_required=True,
            )
        ],
        Incident: [Incident(title="stale", severity="RED", status="verified", finding_ids=[])],
        AgentFinding: [
            AgentFinding(
                agent_name="power_orbit_agent",
                severity="RED",
                confidence=0.9,
                affected_assets=[],
                finding="stale",
                evidence=[],
                recommended_actions=[],
                finding_signature="stale",
                scenario_time_bucket="stale",
            )
        ],
        TelemetryEvent: [TelemetryEvent(event_type="stale", payload={})],
        AgentStatusEvent: [
            AgentStatusEvent(
                agent_name="power_orbit_agent",
                display_name="Power / Orbit Agent",
                status="stale",
                phase="verify",
                severity="RED",
                message="stale",
                affected_assets=[],
                metadata_={},
            )
        ],
        WorldStateSnapshot: [WorldStateSnapshot(version=99, state=CANONICAL_WORLD_STATE, reason="stale")],
    }


_MODEL_BY_TABLE = {model.__tablename__: model for model in VOLATILE_RESET_MODELS}
