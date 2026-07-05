from __future__ import annotations

import asyncio
from copy import deepcopy
import pytest
from fastapi import HTTPException

from app.agents.commander_agent import build_mission_patch_actions
from app.agents.domain_agents import (
    build_checkpoint_downlink_finding,
    build_radiation_finding,
    build_thermal_finding,
    build_vibration_finding,
    build_workload_finding,
)
from app.agents.power_orbit_agent import build_power_orbit_finding
from app.constants import CANONICAL_WORLD_STATE
from app.db.models import AgentFinding, Approval, Command, Incident, MissionPatch, OutboxEvent
from app.routers.mission_patches import ApprovalRequest, approve_mission_patch, approve_patch_transaction, reject_patch_transaction


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        if self.value is None:
            return []
        if isinstance(self.value, list):
            return self.value
        return [self.value]


class _FakeSession:
    def __init__(self, execute_values: list, get_values: dict | None = None):
        self.execute_values = execute_values
        self.get_values = get_values or {}
        self.added = []
        self.commits = 0

    async def execute(self, _statement):
        return _Result(self.execute_values.pop(0))

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1

    async def get(self, model, key):
        return self.get_values.get((model, key))


def _pending_patch() -> MissionPatch:
    state = _incident_state()
    builders = [
        build_power_orbit_finding,
        build_workload_finding,
        build_thermal_finding,
        build_radiation_finding,
        build_checkpoint_downlink_finding,
        build_vibration_finding,
    ]
    actions = build_mission_patch_actions(state, [finding for builder in builders if (finding := builder(state)) is not None])
    return MissionPatch(
        id="patch-042",
        scenario_run_id="phase-1-run",
        incident_id="incident-1",
        severity="RED",
        status="pending_approval",
        summary="Demo patch.",
        evidence=[],
        actions=actions,
        rollback_plan={},
        approval_required=True,
    )


def _incident_state() -> dict:
    state = deepcopy(CANONICAL_WORLD_STATE)
    state["thermal"]["highest_temp_c"] = 91
    state["nodes"][2]["temp_c"] = 91
    return state


def test_approve_transaction_creates_approval_and_queued_commands() -> None:
    patch = _pending_patch()
    # Values: locked patch, approval lookup, agent-status sync, one per command
    # lookup, then the outbox idempotency checks.
    session = _FakeSession([patch, None, None, *([None] * len(patch.actions)), None, None, None])

    approved_patch, created_approval, created_commands, commands, outbox_keys = asyncio.run(
        approve_patch_transaction(
            session,
            patch_id=patch.id,
            operator_id="operator-a",
            operator_note="approved",
        )
    )

    assert approved_patch.status == "approved"
    assert created_approval is True
    assert created_commands == len(patch.actions)
    assert len(commands) == len(patch.actions)
    assert all(command.status == "queued" for command in commands)
    assert any(command.target_asset_id == "ckpt-184900" for command in commands)
    assert any(command.target_asset_id == "node-a" for command in commands)
    assert session.commits == 1
    assert sum(isinstance(row, Approval) for row in session.added) == 1
    assert sum(isinstance(row, Command) for row in session.added) == len(patch.actions)
    assert sum(isinstance(row, OutboxEvent) for row in session.added) == 3
    assert set(outbox_keys) == {
        "outbox:patch-042:command.batch_created",
        "outbox:patch-042:command.batch_created:ui_events",
        "outbox:patch-042:mission_patch.approved",
    }
    assert [row.event_type for row in session.added if isinstance(row, OutboxEvent)].count("command.batch_created") == 2
    assert [row.event_type for row in session.added if isinstance(row, OutboxEvent)].count("mission_patch.approved") == 1


def test_approve_transaction_is_noop_for_already_approved_patch() -> None:
    patch = _pending_patch()
    patch.status = "approved"
    existing_commands = [
        Command(
            id="command-1",
            mission_patch_id=patch.id,
            action_type="run_health_check",
            target_asset_id="node-a",
            status="queued",
            input={"type": "run_health_check", "asset_id": "node-a", "check_suite": "distributed_training"},
            result={},
            idempotency_key="command:existing",
        )
    ]
    session = _FakeSession([patch, existing_commands])

    approved_patch, created_approval, created_commands, commands, outbox_keys = asyncio.run(
        approve_patch_transaction(
            session,
            patch_id=patch.id,
            operator_id="operator-b",
            operator_note="duplicate",
        )
    )

    assert approved_patch.status == "approved"
    assert created_approval is False
    assert created_commands == 0
    assert commands == existing_commands
    assert outbox_keys == []
    assert session.added == []
    assert session.commits == 0


def test_already_approved_patch_rejects_cross_patch_idempotency_reuse() -> None:
    patch = _pending_patch()
    patch.status = "approved"
    reused_approval = Approval(
        mission_patch_id="other-patch",
        status="approved",
        operator_id="operator-a",
        idempotency_key="shared-key",
    )
    session = _FakeSession([patch, reused_approval])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            approve_patch_transaction(
                session,
                patch_id=patch.id,
                operator_id="operator-a",
                operator_note=None,
                idempotency_key="shared-key",
            )
        )

    assert exc_info.value.status_code == 409
    assert session.commits == 0


def test_approve_transaction_rejects_cross_patch_idempotency_reuse() -> None:
    patch = _pending_patch()
    reused_approval = Approval(
        mission_patch_id="other-patch",
        status="approved",
        operator_id="operator-a",
        idempotency_key="shared-key",
    )
    session = _FakeSession([patch, reused_approval])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            approve_patch_transaction(
                session,
                patch_id=patch.id,
                operator_id="operator-a",
                operator_note=None,
                idempotency_key="shared-key",
            )
        )

    assert exc_info.value.status_code == 409
    assert "Idempotency-Key" in exc_info.value.detail
    assert session.commits == 0


def test_approve_route_returns_existing_commands_for_repeat_approval(monkeypatch) -> None:
    patch = _pending_patch()
    patch.status = "approved"
    command = Command(
        id="command-1",
        mission_patch_id=patch.id,
        action_type="run_health_check",
        target_asset_id="node-a",
        status="queued",
        input={"type": "run_health_check", "asset_id": "node-a", "check_suite": "distributed_training"},
        result={},
        idempotency_key="command:existing",
    )

    async def fake_publish(_keys):
        return 0

    monkeypatch.setattr("app.routers.mission_patches.publish_outbox_events_by_keys", fake_publish)
    session = _FakeSession([patch, [command]])

    response = asyncio.run(
        approve_mission_patch(
            patch.id,
            body=ApprovalRequest(operator_id="operator-b", operator_note="repeat"),
            session=session,
        )
    )

    assert response["commands_created"] == 0
    assert response["commands"][0]["id"] == "command-1"
    assert response["commands"][0]["status"] == "queued"


def test_reject_transaction_updates_patch_and_incident_once() -> None:
    patch = _pending_patch()
    incident = Incident(
        id="incident-1",
        scenario_run_id="phase-1-run",
        incident_key="training_continuity_risk:llm-train-042:combined",
        title="Training continuity risk",
        severity="RED",
        status="pending_approval",
        finding_ids=[],
        summary="Demo incident.",
    )
    session = _FakeSession(
        [patch, None, None, None],
        get_values={(Incident, "incident-1"): incident},
    )

    rejected_patch, created_rejection, outbox_keys = asyncio.run(
        reject_patch_transaction(
            session,
            patch_id=patch.id,
            operator_id="operator-a",
            operator_note="reject",
        )
    )

    assert rejected_patch.status == "rejected"
    assert incident.status == "rejected"
    assert created_rejection is True
    assert outbox_keys == ["outbox:patch-042:mission_patch.rejected"]
    assert session.commits == 1
    assert sum(isinstance(row, Approval) and row.status == "rejected" for row in session.added) == 1
    assert sum(isinstance(row, OutboxEvent) and row.event_type == "mission_patch.rejected" for row in session.added) == 1


def test_reject_transaction_closes_grouped_findings() -> None:
    patch = _pending_patch()
    open_finding = AgentFinding(
        id="finding-1",
        scenario_run_id="phase-1-run",
        agent_name="thermal_physical_agent",
        severity="RED",
        confidence=0.9,
        affected_assets=["node-c"],
        finding="Node C hotspot is above safe thermal threshold.",
        evidence=[],
        risk="Node C should not receive critical workloads.",
        recommended_actions=["mark_node_suspect"],
        status="open",
        finding_signature="thermal_node_c_hotspot",
        scenario_time_bucket="phase4-demo",
    )
    resolved_finding = AgentFinding(
        id="finding-2",
        scenario_run_id="phase-1-run",
        agent_name="workload_agent",
        severity="ORANGE",
        confidence=0.8,
        affected_assets=["node-a"],
        finding="Rank lag detected.",
        evidence=[],
        risk="Throughput may stall.",
        recommended_actions=["run_health_check"],
        status="resolved",
        finding_signature="workload_rank_lag",
        scenario_time_bucket="phase4-demo",
    )
    incident = Incident(
        id="incident-1",
        scenario_run_id="phase-1-run",
        incident_key="training_continuity_risk:llm-train-042:combined",
        title="Training continuity risk",
        severity="RED",
        status="pending_approval",
        finding_ids=["finding-1", "finding-2"],
        summary="Demo incident.",
    )
    session = _FakeSession(
        [patch, None, None, [open_finding, resolved_finding], None],
        get_values={(Incident, "incident-1"): incident},
    )

    rejected_patch, created_rejection, _outbox_keys = asyncio.run(
        reject_patch_transaction(
            session,
            patch_id=patch.id,
            operator_id="operator-a",
            operator_note="reject",
        )
    )

    assert rejected_patch.status == "rejected"
    assert created_rejection is True
    assert incident.status == "rejected"
    # Open findings close so the Commander cannot immediately re-propose the
    # same patch; findings already in a terminal state are left untouched.
    assert open_finding.status == "rejected"
    assert resolved_finding.status == "resolved"


def test_reject_transaction_is_noop_for_already_rejected_patch() -> None:
    patch = _pending_patch()
    patch.status = "rejected"
    session = _FakeSession([patch])

    rejected_patch, created_rejection, outbox_keys = asyncio.run(
        reject_patch_transaction(
            session,
            patch_id=patch.id,
            operator_id="operator-b",
            operator_note="duplicate",
        )
    )

    assert rejected_patch.status == "rejected"
    assert created_rejection is False
    assert outbox_keys == []
    assert session.added == []
    assert session.commits == 0


def test_already_rejected_patch_rejects_cross_patch_idempotency_reuse() -> None:
    patch = _pending_patch()
    patch.status = "rejected"
    reused_rejection = Approval(
        mission_patch_id="other-patch",
        status="rejected",
        operator_id="operator-a",
        idempotency_key="shared-key",
    )
    session = _FakeSession([patch, reused_rejection])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            reject_patch_transaction(
                session,
                patch_id=patch.id,
                operator_id="operator-a",
                operator_note=None,
                idempotency_key="shared-key",
            )
        )

    assert exc_info.value.status_code == 409
    assert session.commits == 0


def test_reject_transaction_rejects_cross_patch_idempotency_reuse() -> None:
    patch = _pending_patch()
    reused_rejection = Approval(
        mission_patch_id="other-patch",
        status="rejected",
        operator_id="operator-a",
        idempotency_key="shared-key",
    )
    session = _FakeSession([patch, reused_rejection])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            reject_patch_transaction(
                session,
                patch_id=patch.id,
                operator_id="operator-a",
                operator_note=None,
                idempotency_key="shared-key",
            )
        )

    assert exc_info.value.status_code == 409
    assert "Idempotency-Key" in exc_info.value.detail
    assert session.commits == 0


def test_reject_transaction_blocks_already_approved_patch() -> None:
    patch = _pending_patch()
    patch.status = "approved"
    session = _FakeSession([patch])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            reject_patch_transaction(
                session,
                patch_id=patch.id,
                operator_id="operator-a",
                operator_note=None,
            )
        )

    assert exc_info.value.status_code == 409
    assert session.commits == 0


def test_approve_transaction_blocks_rejected_patch() -> None:
    patch = _pending_patch()
    patch.status = "rejected"
    session = _FakeSession([patch])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            approve_patch_transaction(
                session,
                patch_id=patch.id,
                operator_id="operator-a",
                operator_note=None,
            )
        )

    assert exc_info.value.status_code == 409
    assert session.commits == 0
