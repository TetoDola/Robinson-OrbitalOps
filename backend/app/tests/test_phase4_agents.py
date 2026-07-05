from __future__ import annotations

from copy import deepcopy
import inspect

from app.agents import domain_agents
from app.agents.domain_agents import (
    AGENT_BUILDERS,
    PHASE4_AGENT_NAMES,
    build_checkpoint_downlink_finding,
    build_radiation_finding,
    build_thermal_finding,
    build_vibration_finding,
    build_workload_finding,
    emit_phase4_heartbeats_once,
    heartbeat_status_payload,
    plan_downlink_chunks,
)
from app.constants import CANONICAL_WORLD_STATE, DEMO_BASELINE_WORLD_STATE


def _incident_state() -> dict:
    state = deepcopy(CANONICAL_WORLD_STATE)
    state["thermal"]["highest_temp_c"] = 91
    state["nodes"][2]["temp_c"] = 91
    return state


def test_remaining_agents_emit_shared_finding_shape() -> None:
    state = _incident_state()
    builders = [
        build_workload_finding,
        build_thermal_finding,
        build_radiation_finding,
        build_checkpoint_downlink_finding,
        build_vibration_finding,
    ]
    for builder in builders:
        finding = builder(state)
        assert finding is not None
        assert set(finding) == {
            "agent_name",
            "severity",
            "confidence",
            "affected_assets",
            "finding",
            "evidence",
            "risk",
            "recommended_actions",
            "finding_signature",
            "scenario_time_bucket",
        }


def test_downlink_bulk_request_produces_chunked_transfer_plan() -> None:
    state = deepcopy(CANONICAL_WORLD_STATE)
    state["downlink"]["pending_request"] = {
        "id": "req-model-export-01",
        "requested_by": "ground-ops",
        "description": "full model weights export",
        "size_gb": 5120,
        "priority": "high",
    }

    plan = plan_downlink_chunks(state["downlink"])
    assert plan is not None
    assert plan["window_capacity_gb"] == 22
    assert plan["chunk_gb"] == 18  # floor(22 * 0.85)
    assert plan["chunk_count"] == 285  # ceil(5120 / 18)
    assert plan["orbits_needed"] == 285
    assert plan["estimated_days"] == 18.3

    finding = build_checkpoint_downlink_finding(state)
    assert finding is not None
    assert finding["finding_signature"] == "downlink_chunked_transfer_plan"
    assert "req-model-export-01" in finding["affected_assets"]
    evidence_text = " ".join(finding["evidence"])
    assert "5.0 TB" in evidence_text
    assert "285 chunks" in evidence_text
    assert "285 orbits" in evidence_text
    assert "18.3 days" in evidence_text


def test_downlink_without_request_keeps_checkpoint_fit_finding() -> None:
    finding = build_checkpoint_downlink_finding(deepcopy(CANONICAL_WORLD_STATE))
    assert finding is not None
    assert finding["finding_signature"] == "downlink_checkpoint_fit"


def test_phase4_has_five_remaining_agent_builders() -> None:
    assert len(AGENT_BUILDERS) == 5
    assert PHASE4_AGENT_NAMES == [
        "workload_agent",
        "thermal_physical_agent",
        "radiation_integrity_agent",
        "checkpoint_downlink_agent",
        "vibration_health_agent",
    ]


def test_phase4_heartbeat_emitter_exists() -> None:
    assert callable(emit_phase4_heartbeats_once)


def test_heartbeat_preserves_active_agent_status() -> None:
    current = type(
        "Status",
        (),
        {
            "status": "proposing",
            "phase": "propose",
            "severity": "RED",
            "message": "Finding sent to Commander.",
        },
    )()

    assert heartbeat_status_payload(current) == {
        "status": "proposing",
        "phase": "propose",
        "severity": "RED",
        "message": "Finding sent to Commander.",
    }


def test_duplicate_finding_check_happens_before_status_emit() -> None:
    source = inspect.getsource(domain_agents._persist_finding)
    assert source.index("find_existing_open_finding") < source.index('status="explaining"')


def test_radiation_agent_uses_computed_risk_data_with_integrity_signal() -> None:
    state = deepcopy(DEMO_BASELINE_WORLD_STATE)
    state["radiation"].update(
        {
            "ecc_errors_last_5min": 120,
            "xid_event": False,
            "computed_risk": {
                "available": True,
                "radiationRiskScore": 78,
                "radiationLevel": "HIGH",
                "mainCause": "Van Allen",
                "sourceMode": "mock",
            },
        }
    )
    state["training"].update(
        {
            "latest_checkpoint": "ckpt-184760",
            "latest_checkpoint_status": "suspect",
            "loss_state": "finite",
        }
    )

    finding = build_radiation_finding(state)

    assert finding is not None
    assert finding["severity"] == "ORANGE"
    assert "ckpt-184760" in finding["affected_assets"]
    assert "Computed radiation risk is HIGH (78/100)." in finding["evidence"]
    assert "Dominant radiation driver is Van Allen." in finding["evidence"]
