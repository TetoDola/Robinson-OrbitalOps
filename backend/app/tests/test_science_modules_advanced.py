from __future__ import annotations

import math

from app.main import app
from app.models import CheckpointStatus, GroundAckStatus, OrbitPhase, SchedulerState
from app.science.calculation_modules import ScientificPredictionEngine
from app.simulator.scenarios import scenario_snapshots
from fastapi.testclient import TestClient


def metric(module, name: str):
    for item in module.metrics:
        if item.name == name:
            return item.value
    raise AssertionError(f"missing metric {name}")


def metric_from_json(module: dict, name: str):
    for item in module["metrics"]:
        if item["name"] == name:
            return item["value"]
    raise AssertionError(f"missing metric {name}")


def noisy_or_expected(pairs: list[tuple[float, float]]) -> float:
    p_no_event = 1.0
    for probability, weight in pairs:
        p_no_event *= 1 - probability * weight
    return round(100 * (1 - p_no_event), 1)


def test_workload_noisy_or_matches_reported_risk():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "scheduler_state": SchedulerState.RUNNING,
            "gpu_utilization_percent": 82,
            "gpu_memory_used_gb": 128,
            "gpu_memory_total_gb": 192,
            "active_cuda_process_count": 0,
            "scheduler_registered_process_count": 0,
            "active_cuda_processes_not_in_scheduler": 0,
            "process_accounting_status": "MISSING",
            "rank_progress_skew": 0,
            "current_step_duration_seconds": 10,
            "rolling_p95_step_duration_seconds": 10,
            "nccl_warning_count": 0,
            "interconnect_error_rate": 0,
            "pcie_replay_count": 0,
            "nvlink_error_count": 0,
        }
    )

    module = ScientificPredictionEngine().workload_gpu(snapshot)
    expected = noisy_or_expected(
        [
            (float(metric(module, "Residency watch probability")), 0.45),
            (float(metric(module, "Orphan worker probability")), 0.85),
            (float(metric(module, "Residual memory probability")), 0.75),
            (float(metric(module, "All-reduce stall probability")), 0.85),
            (float(metric(module, "Interconnect degradation probability")), 0.70),
            (float(metric(module, "Telemetry gap probability")), 0.40),
        ]
    )

    assert module.risk_score == expected
    assert module.predicted_event == "GPU residency with telemetry/process-accounting gap"
    assert module.evidence["top_hypotheses"][0]["name"] == "telemetry_gap"


def test_workload_legitimate_high_load_keeps_orphan_probability_low():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "scheduler_state": SchedulerState.RUNNING,
            "gpu_utilization_percent": 94,
            "gpu_memory_used_gb": 160,
            "gpu_memory_total_gb": 192,
            "active_cuda_process_count": 4,
            "scheduler_registered_process_count": 4,
            "active_cuda_processes_not_in_scheduler": 0,
            "process_accounting_status": "OK",
        }
    )

    module = ScientificPredictionEngine().workload_gpu(snapshot)

    assert module.predicted_event != "orphan worker suspected"
    assert float(metric(module, "Legitimate job running")) == 1
    assert float(metric(module, "Orphan worker probability")) < 0.25


def test_commander_safety_gate_blocks_destructive_workload_action():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "scheduler_state": SchedulerState.IDLE,
            "gpu_utilization_percent": 96,
            "gpu_memory_used_gb": 176,
            "gpu_temperature_celsius": 98,
            "radiator_temperature_celsius": 70,
            "active_cuda_process_count": 3,
            "scheduler_registered_process_count": 0,
            "active_cuda_processes_not_in_scheduler": 3,
            "downlink_available_mbps": 8,
            "downlink_window_seconds": 300,
            "checkpoint_latest_size_gb": 120,
            "checkpoint_full_size_gb": 120,
            "checkpoint_latest_status": CheckpointStatus.SUSPECT,
            "checkpoint_hash_verified": False,
            "canary_eval_score": 0.75,
        }
    )

    assessment = ScientificPredictionEngine().assess(snapshot, 390, [snapshot])
    workload = next(module for module in assessment.modules if module.module_id == "workload_gpu")

    assert workload.requires_human_approval is True
    assert "safety gate active" in workload.dashboard_summary
    assert "Commander safety gate blocks destructive action" in workload.recommended_decision
    assert any(action["type"] == "COMMANDER_SAFETY_GATE" for action in workload.recommended_actions)


def test_thermal_good_radiator_keeps_deficit_negative_and_risk_low():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "gpu_temperature_celsius": 72,
            "radiator_temperature_celsius": 48,
            "gpu_power_watts": 1700,
            "radiator_area_m2": 40,
            "radiator_emissivity": 0.9,
            "radiator_view_factor": 0.95,
            "sun_exposure_factor": 0.1,
        }
    )

    module = ScientificPredictionEngine().thermal_health(snapshot, 0, [(0, snapshot)])

    assert float(metric(module, "Thermal deficit")) < 0
    assert module.risk_score < 42
    assert module.requires_human_approval is False


def test_thermal_fast_history_slope_pushes_forecast_high():
    base = scenario_snapshots()[0]
    history = [
        base.model_copy(update={"timestamp": "2026-07-05T00:00:00Z", "gpu_temperature_celsius": 70, "radiator_temperature_celsius": 45}),
        base.model_copy(update={"timestamp": "2026-07-05T00:15:00Z", "gpu_temperature_celsius": 79, "radiator_temperature_celsius": 50}),
        base.model_copy(update={"timestamp": "2026-07-05T00:30:00Z", "gpu_temperature_celsius": 88, "radiator_temperature_celsius": 56}),
        base.model_copy(update={"timestamp": "2026-07-05T00:45:00Z", "gpu_temperature_celsius": 94, "radiator_temperature_celsius": 62}),
    ]

    assessment = ScientificPredictionEngine().assess(history[-1], 45, history)
    thermal = next(module for module in assessment.modules if module.module_id == "thermal_physical")

    assert thermal.risk_score >= 68
    assert float(metric(thermal, "GPU temperature slope")) > 20
    assert "power limit" in thermal.recommended_decision


def test_power_low_solar_incidence_creates_negative_net_power():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "battery_percent": 46,
            "solar_input_watts": 6500,
            "solar_incidence_angle_deg": 86,
            "spacecraft_base_power_watts": 900,
            "compute_power_watts": 3600,
            "thermal_control_power_watts": 500,
            "downlink_power_watts": 350,
            "battery_capacity_wh": 12_000,
            "eclipse_eta_minutes": 30,
        }
    )

    module = ScientificPredictionEngine().orbit_power(snapshot, 0, [(0, snapshot)])

    assert float(metric(module, "Solar effective power")) < 600
    assert float(metric(module, "Net power")) < 0
    assert module.risk_score >= 42
    assert any(action["type"] == "REDUCE_COMPUTE_POWER_BUDGET" for action in module.recommended_actions)


def test_radiation_bad_hash_and_canary_reduce_checkpoint_trust():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "radiation_dose_rate": 0.15,
            "ecc_corrected_delta": 0,
            "ecc_uncorrected_delta": 0,
            "checkpoint_latest_status": CheckpointStatus.TRUSTED,
            "checkpoint_hash_verified": False,
            "canary_eval_score": 0.80,
        }
    )

    module = ScientificPredictionEngine().radiation_integrity(snapshot, [(0, snapshot)])

    assert float(metric(module, "Checkpoint trust score")) < 85
    assert float(metric(module, "Hash penalty")) > 0
    assert float(metric(module, "Canary penalty")) > 0
    assert any(action["type"] == "RUN_CANARY_VALIDATION" for action in module.recommended_actions)


def test_radiation_saa_solar_event_and_suspect_checkpoint_can_force_rollback():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "orbit_phase": OrbitPhase.HIGH_RADIATION_ZONE,
            "radiation_dose_rate": 2.2,
            "ecc_corrected_delta": 80,
            "ecc_uncorrected_delta": 1,
            "south_atlantic_anomaly_flag": True,
            "solar_particle_event_index": 2.0,
            "checkpoint_latest_status": CheckpointStatus.CORRUPTED,
            "checkpoint_hash_verified": False,
            "canary_eval_score": 0.60,
        }
    )

    module = ScientificPredictionEngine().radiation_integrity(snapshot, [(0, snapshot)])

    assert module.risk_score >= 86
    assert module.requires_human_approval is True
    assert "rollback" in module.recommended_decision
    assert any(action["type"] == "ROLLBACK_TO_LAST_TRUSTED_CHECKPOINT" for action in module.recommended_actions)


def test_downlink_full_checkpoint_fits_current_contact():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "downlink_available_mbps": 800,
            "downlink_window_seconds": 1000,
            "checkpoint_latest_size_gb": 40,
            "checkpoint_full_size_gb": 40,
            "checkpoint_delta_size_gb": 8,
            "ground_ack_status": GroundAckStatus.ACKED,
        }
    )

    module = ScientificPredictionEngine().checkpoint_downlink(snapshot, 0, [(0, snapshot)])

    assert module.predicted_event == "full checkpoint fits current contact"
    assert module.recommended_decision == "send full checkpoint"
    assert "full_checkpoint" in str(metric(module, "Selected payloads"))


def test_downlink_future_windows_improve_forecast_fit_ratio():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "downlink_available_mbps": 8,
            "downlink_window_seconds": 300,
            "checkpoint_latest_size_gb": 90,
            "checkpoint_full_size_gb": 90,
            "future_contact_windows": [
                {"mbps": 120, "seconds": 1200},
                {"mbps": 150, "seconds": 1800},
            ],
        }
    )

    module = ScientificPredictionEngine().checkpoint_downlink(snapshot, 0, [(0, snapshot)])

    assert float(metric(module, "Forecast fit ratio")) > float(metric(module, "Full fit ratio"))
    assert any(action["type"] == "SCHEDULE_FUTURE_FULL_CHECKPOINT" for action in module.recommended_actions)


def test_api_returns_frontend_ready_scientific_contract():
    sample = scenario_snapshots()[0].model_copy(
        update={
            "active_cuda_process_count": 0,
            "process_accounting_status": "MISSING",
            "checkpoint_hash_verified": True,
            "canary_eval_score": 0.98,
        }
    )

    response = TestClient(app).post(
        "/api/science/results",
        json={"samples": [sample.model_dump(mode="json")], "elapsed_minutes": 0},
    )
    body = response.json()

    assert response.status_code == 200
    assert "compound_risk_score" in body
    assert "primary_driver" in body
    for module in body["modules"]:
        assert module["dashboard_summary"]
        assert isinstance(module["evidence"], dict)
        assert isinstance(module["formulas"], dict)
        assert isinstance(module["recommended_actions"], list)
        assert "requires_human_approval" in module


def test_compound_risk_formula_matches_module_confidence_weighting():
    assessment = ScientificPredictionEngine().assess(scenario_snapshots()[0], 0, [scenario_snapshots()[0]])
    p_no_event = 1.0
    for module in assessment.modules:
        p = (module.risk_score / 100) * module.confidence
        p_no_event *= 1 - p
    expected_compound = round(100 * (1 - p_no_event), 1)

    assert math.isclose(assessment.compound_risk_score, expected_compound, abs_tol=0.1)
    assert assessment.overall_risk_score >= assessment.primary_risk_score
