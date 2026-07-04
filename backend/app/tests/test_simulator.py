from __future__ import annotations

from app.constants import DEMO_BASELINE_WORLD_STATE
from app.simulator.state_machine import build_simulated_state, build_telemetry_payload


def test_simulated_state_changes_orbit_and_eclipse_countdown() -> None:
    tick_0 = build_simulated_state(0)
    tick_5 = build_simulated_state(5)

    assert tick_0["satellite"]["lat"] != tick_5["satellite"]["lat"]
    assert tick_0["satellite"]["lon"] != tick_5["satellite"]["lon"]
    assert tick_5["satellite"]["time_to_eclipse_min"] < tick_0["satellite"]["time_to_eclipse_min"]


def test_telemetry_payload_contains_phase2_domains() -> None:
    state = build_simulated_state(5)
    payload = build_telemetry_payload(state)

    assert payload["satellite"]["id"] == "orbital-dc-01"
    assert payload["power"]["battery_percent"] <= 38
    assert payload["thermal"]["hotspot_node"] == "node-c"
    assert payload["radiation"]["ecc_errors_last_5min"] >= 900
    assert payload["downlink"]["capacity_gb"] == 22


def test_tick_zero_is_clean_demo_baseline() -> None:
    state = build_simulated_state(0)

    assert state == DEMO_BASELINE_WORLD_STATE
