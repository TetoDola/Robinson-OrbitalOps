from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.config import settings
from app.services import llm_client
from app.services.operator_chat import build_operator_chat_reply


def _world_state() -> SimpleNamespace:
    return SimpleNamespace(
        version=12,
        scenario_run_id="demo-run",
        state={
            "scenario": "demo",
            "scenario_name": "Thermal recovery drill",
            "satellite": {
                "lat": 47.3,
                "lon": 8.5,
                "alt_km": 550,
                "velocity_km_s": 8.05,
                "time_to_eclipse_min": 6.1,
                "orbit_phase": "sunlight",
                "ground_link": "Zurich-03",
            },
            "power": {
                "battery_percent": 31,
                "solar_kw": 11.4,
                "compute_budget_kw": 22,
            },
            "thermal": {
                "highest_temp_c": 96.4,
                "hotspot_node": "node-c",
                "cooling_status": "degraded",
            },
            "radiation": {
                "risk": "HIGH",
                "region": "South Atlantic Anomaly edge",
                "ecc_errors_last_5min": 910,
                "xid_event": True,
            },
            "downlink": {
                "window_open": True,
                "capacity_gb": 18,
                "used_gb": 4,
                "time_remaining_min": 8,
            },
            "training": {
                "latest_checkpoint": "ckpt-184900",
                "latest_checkpoint_status": "suspect",
                "last_trusted_checkpoint": "ckpt-184500",
            },
            "nodes": [
                {"id": "node-a", "temp_c": 72},
                {"id": "node-c", "temp_c": 96.4},
            ],
        },
    )


def _disable_llm(monkeypatch) -> None:
    monkeypatch.setattr(settings, "crusoe_enabled", False)
    monkeypatch.setattr(settings, "crusoe_api_key", None)
    monkeypatch.setattr(settings, "openrouter_enabled", False)
    monkeypatch.setattr(settings, "openrouter_api_key", None)


def test_operator_chat_falls_back_to_backend_context_when_crusoe_disabled(monkeypatch) -> None:
    _disable_llm(monkeypatch)

    reply = asyncio.run(
        build_operator_chat_reply(
            message="Explain the eclipse risk",
            history=[],
            world_state=_world_state(),
            agents=[],
            findings=[],
            mission_patch=None,
        )
    )

    assert reply.source == "deterministic"
    assert "battery is 31%" in reply.content
    assert "eclipse is in 6.1 min" in reply.content
    assert reply.context_summary["scenario"] == "Thermal recovery drill"


def test_operator_chat_patch_reply_preserves_human_approval_boundary(monkeypatch) -> None:
    _disable_llm(monkeypatch)
    patch = SimpleNamespace(
        id="patch-042",
        severity="RED",
        status="pending_approval",
        summary="Roll back to ckpt-184500 and cordon node-c before eclipse.",
        actions=[
            {"type": "rollback_training", "job_id": "llm-train-042"},
            {"type": "cordon_node", "node_id": "node-c"},
        ],
        approval_required=True,
    )

    reply = asyncio.run(
        build_operator_chat_reply(
            message="Can you approve the patch?",
            history=[],
            world_state=_world_state(),
            agents=[],
            findings=[],
            mission_patch=patch,
        )
    )

    assert reply.source == "deterministic"
    assert "Active mission patch patch-042 is pending_approval" in reply.content
    assert "Approval required: yes" in reply.content
    assert reply.context_summary["active_patch_id"] == "patch-042"


def test_operator_chat_answers_current_altitude_from_world_state(monkeypatch) -> None:
    _disable_llm(monkeypatch)

    reply = asyncio.run(
        build_operator_chat_reply(
            message="what is the current altitude?",
            history=[],
            world_state=_world_state(),
            agents=[],
            findings=[],
            mission_patch=None,
        )
    )

    assert reply.source == "deterministic"
    assert "current altitude is 550 km" in reply.content
    assert "velocity is 8.05 km/s" in reply.content


def test_operator_chat_answers_specific_node_and_rack_temperatures(monkeypatch) -> None:
    _disable_llm(monkeypatch)

    node_reply = asyncio.run(
        build_operator_chat_reply(
            message="what is the temperature on node c?",
            history=[],
            world_state=_world_state(),
            agents=[],
            findings=[],
            mission_patch=None,
        )
    )
    rack_reply = asyncio.run(
        build_operator_chat_reply(
            message="temperature on c rack",
            history=[],
            world_state=_world_state(),
            agents=[],
            findings=[],
            mission_patch=None,
        )
    )

    assert "node-c temperature is 96.4 C" in node_reply.content
    assert "status is unknown" in node_reply.content
    assert "node-c temperature is 96.4 C" in rack_reply.content


def test_operator_chat_can_lookup_all_accessible_backend_data(monkeypatch) -> None:
    _disable_llm(monkeypatch)
    scenario = SimpleNamespace(
        id="demo-run",
        scenario_name="Thermal recovery drill",
        status="paused",
        metadata_={"manual_injection": "thermal-frame"},
        started_at="2026-07-05T08:00:00Z",
        ended_at=None,
    )
    telemetry = SimpleNamespace(
        id=7,
        scenario_run_id="demo-run",
        event_type="power.bus",
        asset_id="orbital-dc-01",
        severity="INFO",
        payload={"bus_voltage": 48.2, "bus_current": 12.4},
        created_at="2026-07-05T08:01:00Z",
    )

    scenario_reply = asyncio.run(
        build_operator_chat_reply(
            message="what is the scenario status?",
            history=[],
            world_state=_world_state(),
            scenario_runs=[scenario],
            agents=[],
            findings=[],
            mission_patch=None,
        )
    )
    telemetry_reply = asyncio.run(
        build_operator_chat_reply(
            message="what is the bus voltage?",
            history=[],
            world_state=_world_state(),
            telemetry_events=[telemetry],
            agents=[],
            findings=[],
            mission_patch=None,
        )
    )

    assert "scenario_runs[demo-run].status = paused" in scenario_reply.content
    assert "telemetry_events[power.bus].payload.bus_voltage = 48.2" in telemetry_reply.content


def test_operator_chat_sends_named_mission_variables_to_crusoe(monkeypatch) -> None:
    monkeypatch.setattr(settings, "crusoe_enabled", True)
    monkeypatch.setattr(settings, "crusoe_api_key", "test-key")
    captured: dict = {}

    async def fake_completion(**kwargs):
        captured.update(kwargs)
        return {"choices": [{"message": {"content": "Node C is the highest thermal concern."}}]}

    monkeypatch.setattr(llm_client, "_crusoe_chat_completion", fake_completion)
    patch = SimpleNamespace(
        id="patch-042",
        incident_id="incident-1",
        severity="RED",
        status="pending_approval",
        summary="Cordon node-c and roll back to ckpt-184500.",
        evidence=[],
        actions=[
            {"type": "rollback_training", "job_id": "llm-train-042", "checkpoint_id": "ckpt-184500"},
            {"type": "cordon_node", "node_id": "node-c"},
        ],
        rollback_plan={"if_verification_fails": ["pause_job"]},
        approval_required=True,
    )
    command = SimpleNamespace(
        id="cmd-1",
        mission_patch_id="patch-042",
        action_type="cordon_node",
        target_asset_id="node-c",
        status="queued",
        input={"type": "cordon_node", "node_id": "node-c"},
        result={},
        created_at="2026-07-05T08:00:00Z",
    )

    reply = asyncio.run(
        build_operator_chat_reply(
            message="What should I inspect?",
            history=[],
            world_state=_world_state(),
            agents=[
                SimpleNamespace(
                    agent="thermal_physical_agent",
                    display_name="Thermal / Physical Agent",
                    status="awaiting_approval",
                    phase="approve",
                    severity="RED",
                    message="Node C hotspot requires approval.",
                    linked_mission_patch_id="patch-042",
                )
            ],
            findings=[],
            mission_patch=patch,
            commands=[command],
        )
    )

    prompt = captured["messages"][-1]["content"]
    assert reply.source == "crusoe"
    assert reply.content == "Node C is the highest thermal concern."
    assert "PRIORITY_VARIABLES" in prompt
    assert "MISSION_VARIABLES_JSON" in prompt
    assert '"thermal_highest_temp_c": 96.4' in prompt
    assert '"thermal_hotspot_node": "node-c"' in prompt
    assert '"active_patch_action_count": 2' in prompt
    assert '"command_status_counts": {"queued": 1}' in prompt
    assert '"all_accessible_data"' in prompt
    assert "OPERATOR_QUESTION=What should I inspect?" in prompt
    assert reply.context_summary["command_count"] == 1
    assert reply.context_summary["queued_commands"] == 1


def test_operator_chat_does_not_short_circuit_direct_questions_when_crusoe_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "crusoe_enabled", True)
    monkeypatch.setattr(settings, "crusoe_api_key", "test-key")
    captured: dict = {}

    async def fake_completion(**kwargs):
        captured.update(kwargs)
        return {"choices": [{"message": {"content": "The LLM saw node-c at 96.4 C."}}]}

    monkeypatch.setattr(llm_client, "_crusoe_chat_completion", fake_completion)

    reply = asyncio.run(
        build_operator_chat_reply(
            message="what is the temperature on node c?",
            history=[],
            world_state=_world_state(),
            agents=[],
            findings=[],
            mission_patch=None,
        )
    )

    prompt = captured["messages"][-1]["content"]
    assert reply.source == "crusoe"
    assert reply.content == "The LLM saw node-c at 96.4 C."
    assert '"nodes": [{"id": "node-a"' in prompt
    assert '"thermal_highest_temp_c": 96.4' in prompt
    assert "OPERATOR_QUESTION=what is the temperature on node c?" in prompt
