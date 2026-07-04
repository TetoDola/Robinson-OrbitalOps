from __future__ import annotations

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
from app.simulator.state_machine import build_simulated_state


def test_remaining_agents_emit_shared_finding_shape() -> None:
    state = build_simulated_state(0)
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
