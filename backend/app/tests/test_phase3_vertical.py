from __future__ import annotations

from app.agents.commander_agent import build_mission_patch_actions
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
    finding = build_power_orbit_finding(CANONICAL_WORLD_STATE)
    assert finding is not None

    actions = build_mission_patch_actions(CANONICAL_WORLD_STATE, [finding])

    assert [action["type"] for action in actions] == [
        "mark_checkpoint_suspect",
        "rollback_training",
        "set_gpu_power_limit",
        "increase_checkpoint_frequency",
        "transfer_priority",
    ]


def test_executor_maps_patch_actions_to_world_state_patches() -> None:
    finding = build_power_orbit_finding(CANONICAL_WORLD_STATE)
    assert finding is not None
    actions = build_mission_patch_actions(CANONICAL_WORLD_STATE, [finding])
    patches = {action["type"]: apply_action_to_state(action) for action in actions}

    assert all(patches[action["type"]] for action in actions)
    assert patches["mark_checkpoint_suspect"]["training"]["quarantined_checkpoint"] == "ckpt-184900"
    assert patches["rollback_training"]["training"]["current_step"] == 184500
    assert patches["increase_checkpoint_frequency"]["training"]["checkpoint_interval_minutes"] == 15
    assert patches["set_gpu_power_limit"]["training"]["throughput_mode"] == "reduced_safe"
    assert patches["transfer_priority"]["downlink"]["queue"][0] == "checkpoint_manifest"


def test_websocket_has_ui_event_broadcast_loop() -> None:
    assert callable(_broadcast_ui_events)
