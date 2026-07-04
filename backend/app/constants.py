"""Canonical defaults used for Phase 1 seeded demo data."""

from __future__ import annotations

from enum import Enum


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
    "satellite": {
        "id": "sat-demo-01",
        "altitude_km": 420.1,
        "eclipse_minutes_remaining": 18,
        "ground_track": "leo-stable",
    },
    "power": {
        "battery_percent": 92.0,
        "solar_kw": 5.4,
        "load_kw": 3.9,
        "status": "stable",
    },
    "thermal": {"node_a_celsius": 58.0, "node_b_celsius": 55.2, "status": "nominal"},
    "radiation": {
        "ecp_errors_5m": 42,
        "xid_errors": 0,
        "status": "nominal",
    },
    "training": {
        "job_id": "llm-train-042",
        "step": 12_340,
        "status": "running",
        "checkpoint_id": "ckpt-184500",
    },
    "agents": ["workload_agent", "thermal_physical_agent", "power_orbit_agent"],
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
