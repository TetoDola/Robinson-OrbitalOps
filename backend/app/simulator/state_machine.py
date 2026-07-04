"""Deterministic mock scenario state machine."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from app.constants import DEMO_BASELINE_WORLD_STATE

ORBIT_SECONDS = 5400
EARTH_ROTATION_SECONDS = 86164
INCLINATION_DEGREES = 53
INITIAL_LONGITUDE = -122.4


def _wrap180(value: float) -> float:
    return ((value + 180) % 360) - 180


def build_simulated_state(tick: int) -> dict[str, Any]:
    if tick == 0:
        return deepcopy(DEMO_BASELINE_WORLD_STATE)

    state = deepcopy(DEMO_BASELINE_WORLD_STATE)
    theta = 2 * math.pi * ((tick * 30) % ORBIT_SECONDS) / ORBIT_SECONDS
    lat = INCLINATION_DEGREES * math.sin(theta)
    lon = _wrap180(INITIAL_LONGITUDE + 360 * (tick * 30) / ORBIT_SECONDS - 360 * (tick * 30) / EARTH_ROTATION_SECONDS)
    incident_progress = max(0, tick)
    time_to_eclipse = max(0, 31 - incident_progress * 4)
    battery = max(12, 62 - incident_progress * 4.8)
    solar_kw = max(0.0, 11.4 - incident_progress * 2.04)
    node_c_temp = 62 if tick < 2 else min(94, 82 + (tick - 2) * 2)
    ecc_errors = 12 if tick < 3 else min(1200, 700 + (tick - 3) * 110)
    downlink_remaining = max(0, 26 - incident_progress * 2)
    downlink_capacity = 180 if tick < 4 else 22
    incident_active = tick >= 5

    state["tick"] = tick
    state["satellite"].update(
        {
            "lat": round(lat, 3),
            "lon": round(lon, 3),
            "orbit_phase": "eclipse" if time_to_eclipse == 0 else ("approaching_eclipse" if tick >= 4 else "sunlight"),
            "time_to_eclipse_min": time_to_eclipse,
        }
    )
    state["power"].update(
        {
            "battery_percent": round(battery, 1),
            "solar_kw": round(solar_kw, 2),
            "mode": "degraded_safe" if battery < 45 else "nominal",
            "cooling_power_kw": 2.1 if incident_active else 1.5,
            "comms_power_kw": 1.0 if incident_active else 0.4,
        }
    )
    state["thermal"].update(
        {
            "highest_temp_c": round(node_c_temp, 1),
            "hotspot_node": "node-c" if tick >= 2 else "none",
            "cooling_status": "degraded" if incident_active else "nominal",
        }
    )
    state["radiation"].update(
        {
            "risk": "elevated" if tick >= 3 else "nominal",
            "region": "risk-zone-alpha" if tick >= 3 else "clear-orbit",
            "ecc_errors_last_5min": ecc_errors,
            "xid_event": tick >= 4,
        }
    )
    state["downlink"].update(
        {
            "window_open": downlink_remaining > 0,
            "capacity_gb": downlink_capacity,
            "time_remaining_min": downlink_remaining,
        }
    )
    state["training"].update(
        {
            "current_step": 184500 + tick * 84,
            "latest_checkpoint": "ckpt-184900" if incident_active else "ckpt-184500",
            "latest_checkpoint_status": "suspect" if incident_active else "trusted",
            "loss_state": "nan_detected" if incident_active else "finite",
        }
    )
    for node in state["nodes"]:
        if node["id"] == "node-a":
            node["status"] = "hot_but_usable" if incident_active else "healthy"
            node["gpu_util"] = 94 if incident_active else 78
            node["temp_c"] = 82 if incident_active else 61
            node["power_w"] = 620 if incident_active else 520
            node["rank_lag"] = 0.08 if incident_active else 0.01
        if node["id"] == "node-c":
            node["status"] = "thermal_physical_risk" if incident_active else "healthy"
            node["temp_c"] = round(node_c_temp, 1)
            node["vibration_score"] = 0.91 if incident_active else 0.15
        if node["id"] == "node-b":
            node["status"] = "integrity_risk" if incident_active else "healthy"
            node["ecc_errors"] = ecc_errors
            node["xid_event"] = tick >= 4
    return state


def build_telemetry_payload(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "tick": state["tick"],
        "satellite": state["satellite"],
        "power": state["power"],
        "thermal": state["thermal"],
        "radiation": state["radiation"],
        "downlink": state["downlink"],
    }
