from __future__ import annotations

from app.models import CheckpointStatus, GroundAckStatus, OrbitPhase, SchedulerState, Severity
from app.main import app
from app.science.calculation_modules import ScientificPredictionEngine
from app.science.reporting import format_scientific_report
from app.simulator.scenarios import build_24h_snapshot, scenario_snapshots
from fastapi.testclient import TestClient


def test_scientific_assessment_returns_five_modules():
    snapshot = build_24h_snapshot(390)

    assessment = ScientificPredictionEngine().assess(snapshot, 390)

    assert len(assessment.modules) == 5
    assert assessment.data_mode == "single-sample-hold"
    assert {module.module_id for module in assessment.modules} == {
        "workload_gpu",
        "thermal_physical",
        "orbit_power",
        "radiation_integrity",
        "checkpoint_downlink",
    }
    assert assessment.overall_risk_score >= max(module.risk_score for module in assessment.modules)


def test_scientific_assessment_uses_history_variations_for_prediction():
    base = scenario_snapshots()[0]
    history = [
        base.model_copy(update={"timestamp": "2026-07-05T00:00:00Z", "gpu_temperature_celsius": 70, "radiator_temperature_celsius": 44, "battery_percent": 72}),
        base.model_copy(update={"timestamp": "2026-07-05T00:15:00Z", "gpu_temperature_celsius": 78, "radiator_temperature_celsius": 49, "battery_percent": 64}),
        base.model_copy(update={"timestamp": "2026-07-05T00:30:00Z", "gpu_temperature_celsius": 86, "radiator_temperature_celsius": 55, "battery_percent": 53}),
        base.model_copy(update={"timestamp": "2026-07-05T00:45:00Z", "gpu_temperature_celsius": 92, "radiator_temperature_celsius": 60, "battery_percent": 42}),
    ]

    assessment = ScientificPredictionEngine().assess(history[-1], 45, history)
    thermal = next(module for module in assessment.modules if module.module_id == "thermal_physical")
    power = next(module for module in assessment.modules if module.module_id == "orbit_power")

    assert assessment.data_mode == "history-trend-forecast"
    assert assessment.samples_used == 4
    assert thermal.severity in {Severity.HIGH, Severity.CRITICAL}
    assert any(metric.name == "GPU temperature slope" and float(metric.value) > 20 for metric in thermal.metrics)
    assert power.severity in {Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL}
    assert any(metric.name == "Observed battery slope" and float(metric.value) < 0 for metric in power.metrics)


def test_workload_science_detects_confirmed_orphan_worker_pressure():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "scheduler_state": SchedulerState.IDLE,
            "gpu_utilization_percent": 94,
            "gpu_memory_used_gb": 162,
            "gpu_power_watts": 4100,
            "active_cuda_process_count": 3,
            "scheduler_registered_process_count": 0,
            "active_cuda_processes_not_in_scheduler": 3,
        }
    )

    module = ScientificPredictionEngine().workload_gpu(snapshot)

    assert module.severity in {Severity.HIGH, Severity.CRITICAL}
    assert module.predicted_event == "orphan worker suspected"
    assert module.action_level in {"HIGH", "CRITICAL"}


def test_workload_science_avoids_orphan_label_without_scheduler_or_process_mismatch():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "scheduler_state": SchedulerState.RUNNING,
            "gpu_utilization_percent": 82,
            "gpu_memory_used_gb": 128,
            "gpu_memory_total_gb": 192,
            "active_cuda_process_count": 2,
            "scheduler_registered_process_count": 2,
            "active_cuda_processes_not_in_scheduler": 0,
        }
    )

    module = ScientificPredictionEngine().workload_gpu(snapshot)

    assert module.predicted_event != "orphan worker suspected"
    assert module.recommended_decision == "increase sampling and reconcile CUDA process table with scheduler state"


def test_workload_science_uses_distributed_training_signals_for_all_reduce():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "scheduler_state": SchedulerState.RUNNING,
            "gpu_utilization_percent": 91,
            "rank_progress_skew": 4,
            "current_step_duration_seconds": 42,
            "rolling_p95_step_duration_seconds": 10,
            "nccl_warning_count": 4,
            "interconnect_error_rate": 0.8,
            "power_violation_time_delta_seconds": 12,
        }
    )

    module = ScientificPredictionEngine().workload_gpu(snapshot)

    assert module.predicted_event == "rank all-reduce timeout risk"
    assert module.severity in {Severity.HIGH, Severity.CRITICAL}


def test_workload_v3_flags_telemetry_gap_without_claiming_orphan():
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
        }
    )

    module = ScientificPredictionEngine().workload_gpu(snapshot)

    assert module.predicted_event == "GPU residency with telemetry/process-accounting gap"
    assert module.risk_score >= 55
    assert module.confidence <= 0.7
    assert module.predicted_event != "orphan worker suspected"
    assert any(item["name"] == "telemetry_gap" for item in module.evidence["top_hypotheses"])


def test_thermal_risk_rises_when_radiator_deficit_positive():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "gpu_temperature_celsius": 84,
            "radiator_temperature_celsius": 30,
            "gpu_power_watts": 6200,
            "radiator_area_m2": 0.5,
            "radiator_emissivity": 0.75,
            "radiator_view_factor": 0.8,
            "sun_exposure_factor": 1.0,
        }
    )

    module = ScientificPredictionEngine().thermal_health(snapshot, 0, [(0, snapshot)])

    assert module.risk_score > 68
    assert float(next(metric.value for metric in module.metrics if metric.name == "Thermal deficit")) > 0
    assert "power limit" in module.recommended_decision


def test_power_reserves_cooling_before_compute():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "battery_percent": 39,
            "solar_input_watts": 900,
            "spacecraft_base_power_watts": 800,
            "compute_power_watts": 5200,
            "thermal_control_power_watts": 700,
            "downlink_power_watts": 350,
            "battery_capacity_wh": 12_000,
            "eclipse_eta_minutes": 20,
            "critical_downlink_eta_minutes": 25,
        }
    )

    module = ScientificPredictionEngine().orbit_power(snapshot, 0, [(0, snapshot)])

    assert module.risk_score >= 42
    assert "compute" in module.recommended_decision or "cooling" in module.recommended_decision
    assert any(action["type"] == "REDUCE_COMPUTE_POWER_BUDGET" for action in module.recommended_actions)


def test_downlink_chunking_and_ground_ack_guard():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "downlink_available_mbps": 8,
            "downlink_window_seconds": 600,
            "checkpoint_full_size_gb": 96,
            "checkpoint_latest_size_gb": 96,
            "ground_ack_status": GroundAckStatus.PENDING,
        }
    )

    module = ScientificPredictionEngine().checkpoint_downlink(snapshot, 390, [(0, snapshot)])

    selected_payloads = next(metric.value for metric in module.metrics if metric.name == "Selected payloads")
    chunks = next(metric.value for metric in module.metrics if metric.name == "Checkpoint chunks")
    ack_guard = next(metric.value for metric in module.metrics if metric.name == "Do not delete local checkpoint until ACK")

    assert "manifest" in selected_payloads
    assert "hashes" in selected_payloads
    assert chunks == 96
    assert ack_guard == "true"
    assert any(action["type"] == "DO_NOT_DELETE_LOCAL_CHECKPOINT" for action in module.recommended_actions)


def test_orchestrator_reports_primary_and_compound_risk():
    snapshot = scenario_snapshots()[0]

    assessment = ScientificPredictionEngine().assess(snapshot, 390, [snapshot])

    assert assessment.primary_risk_score == max(module.risk_score for module in assessment.modules)
    assert assessment.compound_risk_score >= assessment.primary_risk_score
    assert assessment.primary_driver
    assert assessment.global_action


def test_radiation_science_marks_uncorrected_ecc_as_high_risk():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "orbit_phase": OrbitPhase.HIGH_RADIATION_ZONE,
            "ecc_corrected_errors": 58,
            "ecc_uncorrected_errors": 1,
            "radiation_dose_rate": 2.1,
            "checkpoint_latest_status": CheckpointStatus.SUSPECT,
        }
    )

    module = ScientificPredictionEngine().radiation_integrity(snapshot, [(390, snapshot)])

    assert module.severity in {Severity.HIGH, Severity.CRITICAL}
    assert "checkpoint" in module.result.lower()


def test_downlink_science_prioritizes_small_evidence_when_full_checkpoint_cannot_fit():
    snapshot = scenario_snapshots()[0].model_copy(
        update={
            "downlink_available_mbps": 8,
            "downlink_window_seconds": 600,
            "checkpoint_latest_size_gb": 96,
        }
    )

    module = ScientificPredictionEngine().checkpoint_downlink(snapshot, 390, [(390, snapshot)])

    assert module.severity in {Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL}
    assert "manifest" in module.recommended_decision
    assert "full checkpoint" in module.result.lower()


def test_scientific_report_contains_formula_explanations():
    assessment = ScientificPredictionEngine().assess(build_24h_snapshot(390), 390)
    report = format_scientific_report(assessment)

    assert "Formules" in report
    assert "Workload-GPU State Reconciliation Agent" in report
    assert "downlink_capacity_gb" in report


def test_science_post_endpoint_accepts_custom_data_series():
    base = scenario_snapshots()[0]
    samples = [
        base.model_copy(update={"timestamp": "2026-07-05T00:00:00Z", "gpu_temperature_celsius": 70, "battery_percent": 72}),
        base.model_copy(update={"timestamp": "2026-07-05T00:15:00Z", "gpu_temperature_celsius": 78, "battery_percent": 62}),
        base.model_copy(update={"timestamp": "2026-07-05T00:30:00Z", "gpu_temperature_celsius": 88, "battery_percent": 49}),
    ]

    response = TestClient(app).post(
        "/api/science/results",
        json={"samples": [sample.model_dump(mode="json") for sample in samples], "elapsed_minutes": 30},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data_mode"] == "history-trend-forecast"
    assert body["samples_used"] == 3
    assert len(body["modules"]) == 5


def test_science_ingest_endpoint_persists_custom_data_for_sql_backed_results():
    base = scenario_snapshots()[0]
    samples = [
        base.model_copy(update={"timestamp": "2026-07-05T02:00:00Z", "gpu_utilization_percent": 40}),
        base.model_copy(update={"timestamp": "2026-07-05T02:15:00Z", "gpu_utilization_percent": 72}),
    ]
    client = TestClient(app)

    ingest_response = client.post(
        "/api/science/ingest",
        json={"samples": [sample.model_dump(mode="json") for sample in samples], "elapsed_minutes": 135},
    )
    results_response = client.get("/api/science/results")

    assert ingest_response.status_code == 200
    assert results_response.status_code == 200
    assert results_response.json()["samples_used"] >= 2
