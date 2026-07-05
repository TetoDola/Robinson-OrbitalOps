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
            "message": "Finding proposed to Commander.",
        },
    )()

    assert heartbeat_status_payload(current) == {
        "status": "proposing",
        "phase": "propose",
        "severity": "RED",
        "message": "Finding proposed to Commander.",
    }


def test_duplicate_finding_check_happens_before_detecting_status() -> None:
    source = inspect.getsource(domain_agents._persist_finding)
    assert source.index("find_existing_open_finding") < source.index('status="detecting"')


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
