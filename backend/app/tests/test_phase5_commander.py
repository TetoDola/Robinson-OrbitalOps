from __future__ import annotations

from copy import deepcopy
import inspect

from app.agents import commander_agent
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
from app.core.safety import validate_mission_patch


def _incident_state() -> dict:
    state = deepcopy(CANONICAL_WORLD_STATE)
    state["thermal"]["highest_temp_c"] = 91
    state["nodes"][2]["temp_c"] = 91
    return state


def _all_seed_findings() -> list[dict]:
    state = _incident_state()
    builders = [
        build_power_orbit_finding,
        build_workload_finding,
        build_thermal_finding,
        build_radiation_finding,
        build_checkpoint_downlink_finding,
        build_vibration_finding,
    ]
    findings = [builder(state) for builder in builders]
    assert all(finding is not None for finding in findings)
    return [finding for finding in findings if finding is not None]


def test_commander_fuses_all_seed_agent_recommendations_into_one_patch_contract() -> None:
    actions = build_mission_patch_actions(CANONICAL_WORLD_STATE, _all_seed_findings())
    action_types = [action["type"] for action in actions]

    assert action_types == [
        "mark_checkpoint_suspect",
        "rollback_training",
        "cordon_node",
        "mark_node_suspect",
        "set_gpu_power_limit",
        "increase_checkpoint_frequency",
        "transfer_priority",
        "snapshot_evidence",
        "run_health_check",
    ]
    assert actions[1]["checkpoint_id"] == "ckpt-184500"
    assert actions[1]["job_id"] == "llm-train-042"
    assert actions[2]["node_id"] == "node-b"
    assert actions[3]["reason"] == "thermal_physical_risk"
    assert actions[6]["send_first"][:2] == ["checkpoint_manifest", "checkpoint_hashes"]
    assert "asset_ids" in actions[7]
    assert actions[8]["check_suite"] == "distributed_training"


def test_safety_validator_allows_seeded_commander_patch_before_approval() -> None:
    actions = build_mission_patch_actions(CANONICAL_WORLD_STATE, _all_seed_findings())
    result = validate_mission_patch(actions, CANONICAL_WORLD_STATE)

    assert result.allowed is True
    assert result.approval_required is True


def test_safety_validator_rejects_rollback_to_suspect_checkpoint() -> None:
    result = validate_mission_patch(
        [{"type": "rollback_training", "job_id": "llm-train-042", "checkpoint_id": "ckpt-184900"}],
        CANONICAL_WORLD_STATE,
    )

    assert result.allowed is False
    assert "only ckpt-184500 is trusted" in result.reason
    assert result.safe_alternative == "rollback_to_ckpt-184500"


def test_safety_validator_rejects_malformed_canonical_payloads() -> None:
    malformed_actions = [
        ({"type": "collect_logs"}, "collect_logs requires asset_id and log_types."),
        ({"type": "mark_checkpoint_suspect"}, "mark_checkpoint_suspect requires checkpoint_id."),
        ({"type": "set_gpu_power_limit", "power_percent": 70}, "set_gpu_power_limit requires node_id."),
    ]

    for action, expected_reason in malformed_actions:
        result = validate_mission_patch([action], CANONICAL_WORLD_STATE)

        assert result.allowed is False
        assert result.reason == expected_reason


def test_commander_sets_pending_approval_only_after_safety_validation() -> None:
    source = inspect.getsource(commander_agent.build_commander_patch)

    assert source.index("validate_mission_patch") < source.index('incident.status = "pending_approval"')
