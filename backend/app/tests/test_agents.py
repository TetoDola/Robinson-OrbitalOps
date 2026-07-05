from __future__ import annotations

from app.agents.checkpoint_downlink_agent import CheckpointDownlinkRecoveryAgent
from app.agents.orbit_power_agent import OrbitPowerAgent
from app.agents.radiation_integrity_agent import RadiationIntegrityAgent
from app.agents.thermal_health_agent import ThermalHealthAgent
from app.agents.workload_gpu_agent import WorkloadGpuAgent
from app.models import CheckpointStatus, GroundAckStatus, OrbitPhase, SchedulerState, Severity
from app.simulator.scenarios import scenario_snapshots


def base_snapshot():
    return scenario_snapshots()[0]


def test_workload_gpu_agent_detects_scheduler_gpu_mismatch():
    snapshot = base_snapshot().model_copy(
        update={
            "scheduler_state": SchedulerState.IDLE,
            "gpu_utilization_percent": 94,
            "gpu_memory_used_gb": 150,
            "gpu_power_watts": 4050,
        }
    )

    findings = WorkloadGpuAgent().analyze(snapshot)

    assert any(finding.severity == Severity.HIGH for finding in findings)
    assert any("Scheduler says IDLE" in " ".join(finding.evidence) for finding in findings)


def test_thermal_health_agent_raises_critical_on_very_high_gpu_temperature():
    snapshot = base_snapshot().model_copy(update={"gpu_temperature_celsius": 98})

    findings = ThermalHealthAgent().analyze(snapshot)

    assert any(finding.severity == Severity.CRITICAL for finding in findings)


def test_orbit_power_agent_raises_high_during_low_battery_eclipse():
    snapshot = base_snapshot().model_copy(
        update={
            "orbit_phase": OrbitPhase.ECLIPSE,
            "battery_percent": 28,
            "solar_input_watts": 100,
        }
    )

    findings = OrbitPowerAgent().analyze(snapshot)

    assert any(finding.severity == Severity.HIGH for finding in findings)


def test_orbit_power_agent_raises_critical_below_survival_margin():
    snapshot = base_snapshot().model_copy(update={"orbit_phase": OrbitPhase.ECLIPSE, "battery_percent": 18})

    findings = OrbitPowerAgent().analyze(snapshot)

    assert any(finding.severity == Severity.CRITICAL for finding in findings)


def test_radiation_integrity_agent_raises_critical_on_uncorrected_ecc():
    snapshot = base_snapshot().model_copy(
        update={
            "orbit_phase": OrbitPhase.HIGH_RADIATION_ZONE,
            "ecc_uncorrected_errors": 1,
            "checkpoint_latest_status": CheckpointStatus.SUSPECT,
        }
    )

    findings = RadiationIntegrityAgent().analyze(snapshot)

    assert any(finding.severity == Severity.CRITICAL for finding in findings)
    assert any(finding.requires_human_approval for finding in findings)


def test_checkpoint_agent_recommends_manifest_hashes_when_full_checkpoint_cannot_fit():
    snapshot = base_snapshot().model_copy(
        update={
            "downlink_available_mbps": 8,
            "downlink_window_seconds": 600,
            "checkpoint_latest_size_gb": 96,
            "checkpoint_latest_status": CheckpointStatus.SUSPECT,
            "ground_ack_status": GroundAckStatus.PENDING,
        }
    )

    findings = CheckpointDownlinkRecoveryAgent().analyze(snapshot)
    recommendations = " ".join(action for finding in findings for action in finding.recommended_actions)

    assert any(finding.severity == Severity.HIGH for finding in findings)
    assert "manifest" in recommendations.lower()
    assert "hashes" in recommendations.lower()
