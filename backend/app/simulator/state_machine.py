"""Deterministic mock scenario state machine."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from app.constants import CANONICAL_WORLD_STATE

ORBIT_SECONDS = 5400
EARTH_ROTATION_SECONDS = 86164
INCLINATION_DEGREES = 53
INITIAL_LONGITUDE = -122.4


def _wrap180(value: float) -> float:
    return ((value + 180) % 360) - 180


def build_simulated_state(tick: int) -> dict[str, Any]:
    state = deepcopy(CANONICAL_WORLD_STATE)
    theta = 2 * math.pi * ((tick * 30) % ORBIT_SECONDS) / ORBIT_SECONDS
    lat = INCLINATION_DEGREES * math.sin(theta)
    lon = _wrap180(INITIAL_LONGITUDE + 360 * (tick * 30) / ORBIT_SECONDS - 360 * (tick * 30) / EARTH_ROTATION_SECONDS)
    time_to_eclipse = max(0, 11 - tick)
    battery = max(12, 38 - tick * 0.7)
    solar_kw = max(0.0, 1.2 - tick * 0.08)
    node_c_temp = min(94, 88 + tick * 0.25)
    ecc_errors = min(1200, 921 + tick * 11)
    downlink_remaining = max(0, 18 - tick)

    state["tick"] = tick
    state["satellite"].update(
        {
            "lat": round(lat, 3),
            "lon": round(lon, 3),
            "orbit_phase": "eclipse" if time_to_eclipse == 0 else "approaching_eclipse",
            "time_to_eclipse_min": time_to_eclipse,
        }
    )
    state["power"].update(
        {
            "battery_percent": round(battery, 1),
            "solar_kw": round(solar_kw, 2),
            "mode": "degraded_safe" if battery < 45 else "nominal",
        }
    )
    state["thermal"].update(
        {
            "highest_temp_c": round(node_c_temp, 1),
            "hotspot_node": "node-c",
            "cooling_status": "degraded",
        }
    )
    state["radiation"].update(
        {
            "risk": "elevated",
            "ecc_errors_last_5min": ecc_errors,
            "xid_event": tick >= 2,
        }
    )
    state["downlink"].update(
        {
            "window_open": downlink_remaining > 0,
            "capacity_gb": 22,
            "time_remaining_min": downlink_remaining,
        }
    )
    for node in state["nodes"]:
        if node["id"] == "node-c":
            node["temp_c"] = round(node_c_temp, 1)
        if node["id"] == "node-b":
            node["ecc_errors"] = ecc_errors
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
