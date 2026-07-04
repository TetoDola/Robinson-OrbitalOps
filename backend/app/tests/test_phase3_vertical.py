from __future__ import annotations

from app.agents.commander_agent import PATCH_ACTIONS
from app.agents.power_orbit_agent import build_power_orbit_finding
from app.constants import CANONICAL_WORLD_STATE
from app.services.command_executor import apply_action_to_state
from app.routers.websocket import _broadcast_ui_events


def test_power_orbit_agent_builds_finding_from_seeded_demo_state() -> None:
    finding = build_power_orbit_finding(CANONICAL_WORLD_STATE)

    assert finding is not None
    assert finding["agent_name"] == "power_orbit_agent"
    assert finding["severity"] == "ORANGE"
    assert "increase_checkpoint_frequency" in finding["recommended_actions"]


def test_commander_patch_actions_are_executable_command_types() -> None:
    assert [action["type"] for action in PATCH_ACTIONS] == [
        "increase_checkpoint_frequency",
        "set_gpu_power_limit",
        "transfer_priority",
    ]


def test_executor_maps_patch_actions_to_world_state_patches() -> None:
    checkpoint_patch = apply_action_to_state(PATCH_ACTIONS[0])
    power_patch = apply_action_to_state(PATCH_ACTIONS[1])
    transfer_patch = apply_action_to_state(PATCH_ACTIONS[2])

    assert checkpoint_patch["training"]["checkpoint_interval_minutes"] == 15
    assert power_patch["training"]["throughput_mode"] == "reduced_safe"
    assert transfer_patch["downlink"]["queue"][0] == "checkpoint_manifest"


def test_websocket_has_ui_event_broadcast_loop() -> None:
    assert callable(_broadcast_ui_events)
