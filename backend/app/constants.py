"""Canonical defaults used for Phase 1 seeded demo data."""

from __future__ import annotations

from enum import Enum


DEMO_SCENARIO_NAME = "training-continuity-demo"
DEMO_SCENARIO_RUN_ID = "phase-1-run"


class StreamName(str, Enum):
    telemetry_events = "telemetry:events"
    agent_status = "agent:status"
    agent_findings = "agent:findings"
    commander_patches = "commander:patches"
    command_requests = "command:requests"
    command_results = "command:results"
    ui_events = "ui:events"


class CommandType(str, Enum):
    collect_logs = "collect_logs"
    snapshot_evidence = "snapshot_evidence"
    increase_monitoring = "increase_monitoring"
    run_health_check = "run_health_check"
    mark_node_suspect = "mark_node_suspect"
    mark_checkpoint_suspect = "mark_checkpoint_suspect"
    rollback_training = "rollback_training"
    cordon_node = "cordon_node"
    pause_job = "pause_job"
    kill_process = "kill_process"
    set_gpu_power_limit = "set_gpu_power_limit"
    increase_checkpoint_frequency = "increase_checkpoint_frequency"
    switch_cooling_loop = "switch_cooling_loop"
    transfer_priority = "transfer_priority"


CANONICAL_WORLD_STATE = {
    "scenario": "phase-1-demo",
    "scenario_name": DEMO_SCENARIO_NAME,
    "tick": 0,
    "satellite": {
        "id": "orbital-dc-01",
        "lat": 0.0,
        "lon": -122.4,
        "alt_km": 550,
        "velocity_km_s": 8.05,
        "orbit_phase": "approaching_eclipse",
        "time_to_eclipse_min": 11,
        "ground_link": "connected",
    },
    "power": {
        "battery_percent": 38,
        "solar_kw": 1.2,
        "compute_budget_kw": 7.5,
        "cooling_power_kw": 2.1,
        "comms_power_kw": 1.0,
        "mode": "degraded_safe",
    },
    "thermal": {
        "highest_temp_c": 86,
        "hotspot_node": "node-c",
        "cooling_status": "degraded",
    },
    "radiation": {
        "risk": "elevated",
        "region": "risk-zone-alpha",
        "ecc_errors_last_5min": 921,
        "xid_event": True,
    },
    "downlink": {
        "window_open": True,
        "capacity_gb": 22,
        "used_gb": 0,
        "time_remaining_min": 18,
    },
    "training": {
        "job_id": "llm-train-042",
        "status": "running",
        "current_step": 184920,
        "last_trusted_checkpoint": "ckpt-184500",
        "latest_checkpoint": "ckpt-184900",
        "latest_checkpoint_status": "suspect",
        "loss_state": "nan_detected",
    },
    "nodes": [
        {
            "id": "node-a",
            "status": "hot_but_usable",
            "gpu_util": 94,
            "temp_c": 82,
            "power_w": 620,
            "rank_lag": 0.08,
        },
        {
            "id": "node-b",
            "status": "integrity_risk",
            "gpu_util": 12,
            "temp_c": 62,
            "ecc_errors": 921,
            "xid_event": True,
        },
        {
            "id": "node-c",
            "status": "thermal_physical_risk",
            "gpu_util": 5,
            "temp_c": 88,
            "vibration_score": 0.91,
        },
    ],
    "agents": [
        "workload_agent",
        "thermal_physical_agent",
        "power_orbit_agent",
        "radiation_integrity_agent",
        "checkpoint_downlink_agent",
        "vibration_health_agent",
        "commander_agent",
    ],
    "active_mission_patch": None,
}


DEMO_BASELINE_WORLD_STATE = {
    "scenario": "phase-1-demo",
    "scenario_name": DEMO_SCENARIO_NAME,
    "tick": 0,
    "satellite": {
        "id": "orbital-dc-01",
        "lat": 0.0,
        "lon": -122.4,
        "alt_km": 550,
        "velocity_km_s": 8.05,
        "orbit_phase": "sunlight",
        "time_to_eclipse_min": 31,
        "ground_link": "connected",
    },
    "power": {
        "battery_percent": 62,
        "solar_kw": 11.4,
        "compute_budget_kw": 7.5,
        "cooling_power_kw": 1.5,
        "comms_power_kw": 0.4,
        "mode": "nominal",
    },
    "thermal": {
        "highest_temp_c": 62,
        "hotspot_node": "none",
        "cooling_status": "nominal",
    },
    "radiation": {
        "risk": "nominal",
        "region": "clear-orbit",
        "ecc_errors_last_5min": 12,
        "xid_event": False,
    },
    "downlink": {
        "window_open": True,
        "capacity_gb": 180,
        "used_gb": 0,
        "time_remaining_min": 26,
    },
    "training": {
        "job_id": "llm-train-042",
        "status": "running",
        "current_step": 184500,
        "last_trusted_checkpoint": "ckpt-184500",
        "latest_checkpoint": "ckpt-184500",
        "latest_checkpoint_status": "trusted",
        "loss_state": "finite",
    },
    "nodes": [
        {
            "id": "node-a",
            "status": "healthy",
            "gpu_util": 78,
            "temp_c": 61,
            "power_w": 520,
            "rank_lag": 0.01,
        },
        {
            "id": "node-b",
            "status": "healthy",
            "gpu_util": 12,
            "temp_c": 58,
            "ecc_errors": 12,
            "xid_event": False,
        },
        {
            "id": "node-c",
            "status": "healthy",
            "gpu_util": 5,
            "temp_c": 60,
            "vibration_score": 0.15,
        },
    ],
    "agents": [
        "workload_agent",
        "thermal_physical_agent",
        "power_orbit_agent",
        "radiation_integrity_agent",
        "checkpoint_downlink_agent",
        "vibration_health_agent",
        "commander_agent",
    ],
    "active_mission_patch": None,
}


AGENT_SEED_STATUS = [
    {
        "agent": "workload_agent",
        "display_name": "Workload Agent",
        "status": "monitoring",
        "phase": "monitor",
        "severity": "INFO",
        "message": "Scheduler and GPU utilization are aligned.",
    },
    {
        "agent": "thermal_physical_agent",
        "display_name": "Thermal / Physical Agent",
        "status": "monitoring",
        "phase": "monitor",
        "severity": "INFO",
        "message": "Node temperatures are in nominal range.",
    },
    {
        "agent": "power_orbit_agent",
        "display_name": "Power / Orbit Agent",
        "status": "monitoring",
        "phase": "monitor",
        "severity": "INFO",
        "message": "Orbit and battery envelope are stable.",
    },
    {
        "agent": "radiation_integrity_agent",
        "display_name": "Radiation / Integrity Agent",
        "status": "healthy",
        "phase": "monitor",
        "severity": "INFO",
        "message": "ECC and NaN checks are within expected envelope.",
    },
    {
        "agent": "checkpoint_downlink_agent",
        "display_name": "Checkpoint / Downlink Agent",
        "status": "monitoring",
        "phase": "monitor",
        "severity": "INFO",
        "message": "Checkpoint size and downlink capacity are healthy.",
    },
    {
        "agent": "vibration_health_agent",
        "display_name": "Vibration Health Agent",
        "status": "monitoring",
        "phase": "monitor",
        "severity": "INFO",
        "message": "No vibration anomalies detected.",
    },
    {
        "agent": "commander_agent",
        "display_name": "Commander Agent",
        "status": "monitoring",
        "phase": "monitor",
        "severity": "INFO",
        "message": "Waiting for findings from domain agents.",
    },
]
