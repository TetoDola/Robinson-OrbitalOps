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

    state["tick"] = tick
    state["satellite"].update(
        {
            "lat": round(lat, 3),
            "lon": round(lon, 3),
            "orbit_phase": "sunlight",
            "time_to_eclipse_min": 31,
        }
    )
    state["training"]["current_step"] = 184500 + tick * 84
    for node in state["nodes"]:
        if node["id"] == "node-a":
            node["gpu_util"] = 76 + round(math.sin(tick / 6) * 2, 1)
        if node["id"] == "node-c":
            node["temp_c"] = 60 + round(math.sin(tick / 5) * 1.5, 1)
        if node["id"] == "node-b":
            node["ecc_errors"] = 12
            node["xid_event"] = False
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
