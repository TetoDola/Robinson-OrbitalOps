from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..models import CheckpointStatus, OrbitPhase, SchedulerState, Severity, TelemetrySnapshot
from .types import CalculationMetric, ModulePredictionResult, ScientificAssessment


BATTERY_CAPACITY_WH = 12_000
BATTERY_RESERVE_TARGET_PERCENT = 35
GPU_THERMAL_LIMIT_C = 95
GPU_CRITICAL_LIMIT_C = 101
SIGMA_STEFAN_BOLTZMANN = 5.670374419e-8
PREDICTION_HORIZON_MINUTES = 180
DEFAULT_STEP_MINUTES = 15
DOWNLINK_PAYLOADS_GB = {
    "manifest": 0.05,
    "hashes": 0.10,
    "ecc_logs": 0.40,
    "thermal_logs": 0.70,
    "workload_logs": 0.95,
    "delta_checkpoint": 18.0,
    "full_checkpoint": 96.0,
}
NUMERIC_LIMITS = {
    "gpu_utilization_percent": (0, 100),
    "gpu_memory_used_gb": (0, 512),
    "gpu_memory_total_gb": (1, 2048),
    "gpu_power_watts": (0, 6500),
    "compute_node_power_watts": (0, 25_000),
    "gpu_temperature_celsius": (-40, 125),
    "board_temperature_celsius": (-40, 100),
    "radiator_temperature_celsius": (-40, 100),
    "battery_percent": (0, 100),
    "solar_input_watts": (0, 9000),
    "spacecraft_power_draw_watts": (0, 9000),
    "downlink_available_mbps": (0, 200),
    "downlink_window_seconds": (0, 86_400),
    "ecc_corrected_errors": (0, 1_000_000),
    "ecc_uncorrected_errors": (0, 1_000_000),
    "radiation_dose_rate": (0, 100),
    "checkpoint_latest_size_gb": (0, 10_000),
    "local_storage_free_gb": (0, 100_000),
    "active_cuda_process_count": (0, 10_000),
    "scheduler_registered_process_count": (0, 10_000),
    "active_cuda_processes_not_in_scheduler": (0, 10_000),
    "time_since_last_job_end_seconds": (0, 86_400),
    "memory_release_delta_gb_per_min": (-10_000, 10_000),
    "rank_progress_skew": (0, 10_000),
    "current_step_duration_seconds": (0, 86_400),
    "rolling_p95_step_duration_seconds": (0.001, 86_400),
    "nccl_warning_count": (0, 1_000_000),
    "interconnect_error_rate": (0, 1_000_000),
    "power_violation_time_delta_seconds": (0, 86_400),
    "xid_error_count": (0, 1_000_000),
    "hbm_temperature_c": (-40, 125),
    "coolant_loop_temperature_c": (-40, 100),
    "radiator_area_m2": (0.1, 100_000),
    "radiator_emissivity": (0.01, 1),
    "radiator_view_factor": (0.01, 1),
    "sun_exposure_factor": (0, 1),
    "spacecraft_base_power_watts": (0, 50_000),
    "compute_power_watts": (0, 50_000),
    "thermal_control_power_watts": (0, 50_000),
    "downlink_power_watts": (0, 50_000),
    "battery_capacity_wh": (100, 10_000_000),
    "solar_incidence_angle_deg": (0, 180),
    "eclipse_eta_minutes": (0, 10_000),
    "radiation_window_eta_minutes": (0, 10_000),
    "critical_downlink_eta_minutes": (0, 10_000),
    "pcie_replay_count": (0, 1_000_000),
    "nvlink_error_count": (0, 1_000_000),
    "bandwidth_drop_percent": (0, 100),
    "stale_telemetry_seconds": (0, 86_400),
    "radiation_dose_accumulated": (0, 1_000_000),
    "orbital_latitude_deg": (-90, 90),
    "altitude_km": (0, 100_000),
    "solar_particle_event_index": (0, 100),
    "ecc_corrected_delta": (0, 1_000_000),
    "ecc_uncorrected_delta": (0, 1_000_000),
    "canary_eval_score": (0, 1),
    "last_trusted_checkpoint_age_minutes": (0, 1_000_000),
    "checkpoint_full_size_gb": (0, 10_000),
    "checkpoint_delta_size_gb": (0, 10_000),
    "manifest_size_gb": (0, 100),
    "hashes_size_gb": (0, 100),
    "ecc_logs_size_gb": (0, 100),
    "thermal_logs_size_gb": (0, 100),
    "workload_logs_size_gb": (0, 100),
    "bit_error_rate": (0, 1),
    "compression_ratio_estimate": (0.01, 1),
}


@dataclass(frozen=True)
class DataTrends:
    samples_used: int
    window_minutes: float
    slopes_per_hour: dict[str, float]
    volatility: dict[str, float]

    def slope(self, field: str) -> float:
        return self.slopes_per_hour.get(field, 0.0)

    def sigma(self, field: str) -> float:
        return self.volatility.get(field, 0.0)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-value))


def noisy_or(probabilities: Iterable[tuple[float, float]]) -> float:
    p_no_event = 1.0
    for probability, weight in probabilities:
        p_no_event *= 1 - clamp(probability, 0.0, 1.0) * clamp(weight, 0.0, 1.0)
    return clamp(1 - p_no_event, 0.0, 1.0)


def noisy_or_risk(module_results: Iterable[ModulePredictionResult]) -> float:
    p_no_event = 1.0
    for result in module_results:
        p = (result.risk_score / 100) * result.confidence
        p_no_event *= 1 - clamp(p, 0.0, 1.0)
    return round(100 * (1 - p_no_event), 1)


def severity_from_score(score: float) -> Severity:
    if score >= 86:
        return Severity.CRITICAL
    if score >= 68:
        return Severity.HIGH
    if score >= 42:
        return Severity.MEDIUM
    if score >= 18:
        return Severity.LOW
    return Severity.INFO


def mission_clock(elapsed_minutes: int) -> str:
    minute = elapsed_minutes % (24 * 60)
    return f"{minute // 60:02d}:{minute % 60:02d}"


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def mission_clock_from_snapshot(snapshot: TelemetrySnapshot, elapsed_minutes: int) -> str:
    timestamp = parse_timestamp(snapshot.timestamp)
    if timestamp:
        return f"{timestamp.hour:02d}:{timestamp.minute:02d}"
    return mission_clock(elapsed_minutes)


def stable_series(snapshot: TelemetrySnapshot, history: list[TelemetrySnapshot] | None) -> list[TelemetrySnapshot]:
    series = list(history or [])
    if not series or series[-1].timestamp != snapshot.timestamp:
        series.append(snapshot)
    timestamps = [parse_timestamp(item.timestamp) for item in series]
    if all(timestamp is not None for timestamp in timestamps):
        return [item for _, item in sorted(zip(timestamps, series), key=lambda pair: pair[0])]
    return series


def series_window_minutes(series: list[TelemetrySnapshot]) -> float:
    if len(series) < 2:
        return 0.0
    first = parse_timestamp(series[0].timestamp)
    last = parse_timestamp(series[-1].timestamp)
    if first and last and last > first:
        return max((last - first).total_seconds() / 60, 0.0)
    return (len(series) - 1) * DEFAULT_STEP_MINUTES


def standard_deviation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def numeric_value(sample: TelemetrySnapshot, field: str) -> float:
    value = getattr(sample, field, None)
    if value is None:
        if field == "compute_node_power_watts":
            return float(sample.gpu_power_watts)
        return 0.0
    return float(value)


def compute_trends(series: list[TelemetrySnapshot]) -> DataTrends:
    window = series_window_minutes(series)
    if len(series) < 2 or window <= 0:
        return DataTrends(samples_used=len(series), window_minutes=window, slopes_per_hour={}, volatility={})

    slopes = {}
    volatility = {}
    for field in NUMERIC_LIMITS:
        values = [numeric_value(sample, field) for sample in series]
        slopes[field] = ((values[-1] - values[0]) / window) * 60
        volatility[field] = standard_deviation(values)
    return DataTrends(samples_used=len(series), window_minutes=round(window, 2), slopes_per_hour=slopes, volatility=volatility)


def forecast_from_data(
    snapshot: TelemetrySnapshot,
    history: list[TelemetrySnapshot] | None,
    horizon_minutes: int,
) -> tuple[list[tuple[int, TelemetrySnapshot]], DataTrends, str]:
    series = stable_series(snapshot, history)
    recent = series[-12:]
    trends = compute_trends(recent)
    data_mode = "history-trend-forecast" if trends.samples_used >= 2 and trends.window_minutes > 0 else "single-sample-hold"
    horizon = []
    for offset in range(0, horizon_minutes + DEFAULT_STEP_MINUTES, DEFAULT_STEP_MINUTES):
        updates = {}
        for field, (lower, upper) in NUMERIC_LIMITS.items():
            current = numeric_value(snapshot, field)
            projected = current + (trends.slope(field) / 60) * offset
            projected = clamp(projected, lower, upper)
            if field in {
                "ecc_corrected_errors",
                "ecc_uncorrected_errors",
                "downlink_window_seconds",
                "active_cuda_process_count",
                "scheduler_registered_process_count",
                "active_cuda_processes_not_in_scheduler",
                "nccl_warning_count",
                "xid_error_count",
            }:
                updates[field] = int(round(projected))
            else:
                updates[field] = round(projected, 3)
        horizon.append((offset, snapshot.model_copy(update=updates)))
    return horizon, trends, data_mode


def first_crossing(samples: Iterable[tuple[int, TelemetrySnapshot]], predicate) -> int | None:
    for elapsed, snapshot in samples:
        if predicate(snapshot):
            return elapsed
    return None


def workload_action(score: float) -> tuple[str, str]:
    if score >= 86:
        return (
            "CRITICAL",
            "quarantine GPU for scheduler reconciliation; terminate orphan process only after validation; alert Commander Agent",
        )
    if score >= 68:
        return ("HIGH", "cordon GPU, block new scheduling, and checkpoint affected job")
    if score >= 42:
        return ("MEDIUM", "increase sampling and reconcile CUDA process table with scheduler state")
    if score >= 18:
        return ("LOW", "continue monitoring with elevated sampling")
    return ("INFO", "continue monitoring")


def action_level_from_score(score: float) -> str:
    if score >= 86:
        return "CRITICAL"
    if score >= 68:
        return "HIGH"
    if score >= 42:
        return "MEDIUM"
    if score >= 18:
        return "LOW"
    return "INFO"


def recommended_action(
    action_type: str,
    reason: str,
    value: str | float | int | None = None,
    approval: bool = False,
    target: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": action_type, "reason": reason, "approval": approval}
    if value is not None:
        payload["value"] = value
    if target is not None:
        payload["target"] = target
    return payload


def metric_lookup(module: ModulePredictionResult, name: str, default: Any = 0) -> Any:
    for metric in module.metrics:
        if metric.name == name:
            return metric.value
    return default


def radiator_heat_rejection_w(
    area_m2: float,
    emissivity: float,
    view_factor: float,
    radiator_temperature_c: float,
    sun_exposure_factor: float = 0.0,
    t_space_k: float = 3.0,
) -> float:
    t_rad_k = radiator_temperature_c + 273.15
    deep_space_radiation = emissivity * SIGMA_STEFAN_BOLTZMANN * area_m2 * view_factor * (t_rad_k**4 - t_space_k**4)
    solar_penalty = 1 - 0.25 * clamp(sun_exposure_factor, 0.0, 1.0)
    return max(0.0, deep_space_radiation * solar_penalty)


def solar_effective_power(panel_power_watts: float, incidence_angle_deg: float | None, degradation: float = 0.0) -> float:
    if incidence_angle_deg is None:
        return panel_power_watts * (1 - degradation)
    angle_factor = max(0.0, math.cos(math.radians(incidence_angle_deg)))
    return panel_power_watts * angle_factor * (1 - degradation)


def downlink_capacity_gb(mbps: float, seconds: float) -> float:
    return max(0.0, mbps * seconds / 8192)


def select_payloads(payloads: list[dict[str, Any]], capacity_gb: float) -> tuple[list[dict[str, Any]], float]:
    selected: list[dict[str, Any]] = []
    remaining = capacity_gb
    for payload in sorted(payloads, key=lambda item: float(item["priority"]), reverse=True):
        size = float(payload["size_gb"])
        if size <= remaining:
            selected.append(payload)
            remaining -= size
    return selected, max(0.0, remaining)


class ScientificPredictionEngine:
    def assess(
        self,
        snapshot: TelemetrySnapshot,
        elapsed_minutes: int = 0,
        history: list[TelemetrySnapshot] | None = None,
    ) -> ScientificAssessment:
        horizon, trends, data_mode = forecast_from_data(snapshot, history, PREDICTION_HORIZON_MINUTES)
        thermal = self.thermal_health(snapshot, elapsed_minutes, horizon, trends)
        power = self.orbit_power(snapshot, elapsed_minutes, horizon, trends)
        radiation = self.radiation_integrity(snapshot, horizon, trends)
        downlink = self.checkpoint_downlink(snapshot, elapsed_minutes, horizon, trends)
        workload = self.commander_safety_gate(
            self.workload_gpu(snapshot, trends),
            thermal=thermal,
            power=power,
            radiation=radiation,
            downlink=downlink,
        )
        modules = [workload, thermal, power, radiation, downlink]
        primary_driver = max(modules, key=lambda module: module.risk_score)
        primary_score = round(primary_driver.risk_score, 1)
        compound_score = noisy_or_risk(modules)
        overall_score = round(max(primary_score, 0.65 * primary_score + 0.35 * compound_score), 1)
        return ScientificAssessment(
            timestamp=snapshot.timestamp,
            mission_clock=mission_clock_from_snapshot(snapshot, elapsed_minutes),
            orbit_phase=snapshot.orbit_phase.value,
            data_mode=data_mode,
            samples_used=trends.samples_used,
            trend_window_minutes=trends.window_minutes,
            overall_risk_score=overall_score,
            overall_severity=severity_from_score(overall_score),
            primary_risk_score=primary_score,
            compound_risk_score=compound_score,
            primary_driver=primary_driver.module_id,
            global_action=self.global_action(overall_score, primary_driver.module_id, compound_score),
            modules=modules,
        )

    def global_action(self, overall_score: float, primary_driver: str, compound_score: float) -> str:
        if overall_score >= 86:
            return f"mission patch required; primary driver {primary_driver}; compound risk {compound_score:.1f}/100"
        if overall_score >= 68:
            return f"operator review required; primary driver {primary_driver}; protect checkpoint before destructive actions"
        if overall_score >= 42:
            return f"increase sampling and reconcile cross-agent constraints; primary driver {primary_driver}"
        return f"continue monitoring; primary driver {primary_driver}"

    def commander_safety_gate(
        self,
        workload: ModulePredictionResult,
        thermal: ModulePredictionResult,
        power: ModulePredictionResult,
        radiation: ModulePredictionResult,
        downlink: ModulePredictionResult,
    ) -> ModulePredictionResult:
        if workload.action_level not in {"HIGH", "CRITICAL"}:
            return workload

        blocked_reasons: list[str] = []
        if thermal.risk_score >= 68:
            blocked_reasons.append("thermal agent predicts unsafe heat margin")
        if power.risk_score >= 68:
            blocked_reasons.append("power agent requires reserve for cooling/downlink")
        if float(metric_lookup(radiation, "Checkpoint trust score", 100)) < 75:
            blocked_reasons.append("checkpoint trust below destructive-action threshold")
        if float(metric_lookup(downlink, "Full fit ratio", 0)) < 0.1:
            blocked_reasons.append("downlink cannot carry full checkpoint in current contact")

        if not blocked_reasons:
            return workload

        evidence = dict(workload.evidence)
        evidence["commander_safety_gate"] = {
            "blocked_reasons": blocked_reasons,
            "thermal_risk": thermal.risk_score,
            "power_risk": power.risk_score,
            "radiation_risk": radiation.risk_score,
            "downlink_risk": downlink.risk_score,
        }
        actions = list(workload.recommended_actions)
        actions.append(
            recommended_action(
                "COMMANDER_SAFETY_GATE",
                "Block destructive GPU action until checkpoint, thermal, power and downlink constraints are acceptable.",
                approval=True,
            )
        )
        decision = f"{workload.recommended_decision}; Commander safety gate blocks destructive action: {', '.join(blocked_reasons)}"
        return workload.model_copy(
            update={
                "recommended_decision": decision,
                "recommended_actions": actions,
                "requires_human_approval": True,
                "evidence": evidence,
                "dashboard_summary": f"{workload.dashboard_summary} | safety gate active",
            }
        )

    def workload_gpu(self, snapshot: TelemetrySnapshot, trends: DataTrends | None = None) -> ModulePredictionResult:
        utilization = snapshot.gpu_utilization_percent / 100
        memory = snapshot.memory_used_percent / 100
        utilization_slope = trends.slope("gpu_utilization_percent") if trends else 0.0
        memory_slope = trends.slope("gpu_memory_used_gb") if trends else 0.0
        utilization_sigma = trends.sigma("gpu_utilization_percent") if trends else 0.0
        node_power_watts = snapshot.compute_node_power_watts if snapshot.compute_node_power_watts is not None else snapshot.gpu_power_watts
        active_cuda_process_count = snapshot.active_cuda_process_count or 0
        scheduler_registered_process_count = snapshot.scheduler_registered_process_count or 0
        process_mismatch_count = (
            snapshot.active_cuda_processes_not_in_scheduler
            if snapshot.active_cuda_processes_not_in_scheduler is not None
            else max(0, active_cuda_process_count - scheduler_registered_process_count)
        )
        scheduler_mismatch = 1.0 if snapshot.scheduler_state in {SchedulerState.IDLE, SchedulerState.FAILED, SchedulerState.UNKNOWN} and utilization > 0.5 else 0.0
        process_mismatch = 1.0 if process_mismatch_count > 0 else 0.0
        legitimate_job_running = 1.0 if snapshot.scheduler_state == SchedulerState.RUNNING and not scheduler_mismatch and not process_mismatch else 0.0
        time_since_job_end_seconds = snapshot.time_since_last_job_end_seconds or 0.0
        time_after_job_norm = min(time_since_job_end_seconds / 600, 1.0)
        memory_release_delta_gb_per_min = snapshot.memory_release_delta_gb_per_min if snapshot.memory_release_delta_gb_per_min is not None else -999.0
        memory_not_released_after_job = 1.0 if time_since_job_end_seconds > 120 and memory > 0.25 and memory_release_delta_gb_per_min > -0.2 else 0.0
        telemetry_contradiction = 1.0 if utilization > 0.5 and snapshot.active_cuda_process_count == 0 else 0.0
        process_accounting_missing = 1.0 if snapshot.process_accounting_status not in {None, "OK"} or snapshot.active_cuda_process_count is None else 0.0
        stale_telemetry = 1.0 if (snapshot.stale_telemetry_seconds or 0.0) > 120 else 0.0
        direct_signal_count = sum(
            1
            for present in [
                snapshot.active_cuda_process_count is not None,
                snapshot.scheduler_registered_process_count is not None,
                snapshot.rank_progress_skew is not None,
                snapshot.current_step_duration_seconds is not None,
                snapshot.nccl_warning_count is not None,
                snapshot.interconnect_error_rate is not None,
                snapshot.pcie_replay_count is not None,
                snapshot.nvlink_error_count is not None,
                snapshot.xid_error_count is not None,
            ]
            if present
        )
        samples_used = trends.samples_used if trends else 1
        telemetry_quality = clamp(
            0.95
            + 0.05 * min(samples_used / 12, 1)
            - 0.25 * telemetry_contradiction
            - 0.08 * process_accounting_missing
            - 0.05 * stale_telemetry,
            0.20,
            0.98,
        )
        residency_score = utilization * memory
        residency_watch_probability = sigmoid(5.0 * (residency_score - 0.45))
        orphan_worker_probability = sigmoid(
            -3.0
            + 5.5 * (residency_score - 0.45)
            + 2.8 * scheduler_mismatch
            + 2.3 * process_mismatch
            + 1.1 * memory_not_released_after_job
            - 0.8 * legitimate_job_running
            + 0.9 * telemetry_contradiction
        )
        residual_memory_probability = sigmoid(
            -3.1
            + 1.3 * memory
            + 2.3 * memory_not_released_after_job
            + 1.5 * time_after_job_norm
            + 0.8 * scheduler_mismatch
        )
        step_time_ratio = (
            snapshot.current_step_duration_seconds / max(snapshot.rolling_p95_step_duration_seconds, 1)
            if snapshot.current_step_duration_seconds and snapshot.rolling_p95_step_duration_seconds
            else 1.0
        )
        step_time_excess = max(0.0, step_time_ratio - 1.0)
        rank_progress_skew_norm = min((snapshot.rank_progress_skew or 0.0) / 3.0, 1.0)
        nccl_warning_norm = min((snapshot.nccl_warning_count or 0) / 5.0, 1.0)
        interconnect_error_norm = min((snapshot.interconnect_error_rate or 0.0) / 10.0, 1.0)
        pcie_replay_norm = min((snapshot.pcie_replay_count or 0) / 100.0, 1.0)
        nvlink_error_norm = min((snapshot.nvlink_error_count or 0) / 50.0, 1.0)
        bandwidth_drop_norm = min((snapshot.bandwidth_drop_percent or 0.0) / 100.0, 1.0)
        ecc_rate_source = snapshot.ecc_corrected_delta if snapshot.ecc_corrected_delta is not None else max(0.0, trends.slope("ecc_corrected_errors") if trends else snapshot.ecc_corrected_errors)
        ecc_corrected_rate_norm = min(max(0.0, float(ecc_rate_source)) / 20.0, 1.0)
        power_throttle_flag = 1.0 if (snapshot.power_violation_time_delta_seconds or 0.0) > 0 else 0.0
        thermal_throttle_flag = 1.0 if snapshot.thermal_throttle_flag else 0.0
        all_reduce_stall_probability = sigmoid(
            -3.0
            + 1.4 * step_time_excess
            + 2.0 * rank_progress_skew_norm
            + 1.3 * nccl_warning_norm
            + 1.4 * interconnect_error_norm
            + 0.7 * pcie_replay_norm
            + 0.6 * ecc_corrected_rate_norm
            + 0.6 * thermal_throttle_flag
            + 0.5 * power_throttle_flag
        )
        interconnect_degradation_probability = sigmoid(
            -2.6
            + 2.2 * nvlink_error_norm
            + 2.0 * pcie_replay_norm
            + 1.3 * bandwidth_drop_norm
            + 1.2 * nccl_warning_norm
        )
        telemetry_gap_probability = sigmoid(
            -2.0
            + 3.2 * telemetry_contradiction
            + 0.8 * process_accounting_missing
            + 0.6 * stale_telemetry
        )
        weighted_probabilities = [
            (residency_watch_probability, 0.45),
            (orphan_worker_probability, 0.85),
            (residual_memory_probability, 0.75),
            (all_reduce_stall_probability, 0.85),
            (interconnect_degradation_probability, 0.70),
            (telemetry_gap_probability, 0.40),
        ]
        risk_score = round(100 * noisy_or(weighted_probabilities), 1)
        hypotheses = {
            "telemetry_gap": telemetry_gap_probability,
            "residency_watch": residency_watch_probability,
            "orphan_worker": orphan_worker_probability,
            "residual_memory": residual_memory_probability,
            "all_reduce_stall": all_reduce_stall_probability,
            "interconnect_degradation": interconnect_degradation_probability,
        }
        top_hypotheses = sorted(hypotheses.items(), key=lambda item: item[1], reverse=True)
        top_name = top_hypotheses[0][0]
        if all_reduce_stall_probability >= 0.68 and all_reduce_stall_probability >= orphan_worker_probability and all_reduce_stall_probability >= interconnect_degradation_probability:
            predicted_event = "rank all-reduce timeout risk"
        elif (scheduler_mismatch or process_mismatch) and orphan_worker_probability >= 0.42:
            predicted_event = "orphan worker suspected"
        elif top_name == "all_reduce_stall" and all_reduce_stall_probability >= 0.42:
            predicted_event = "rank all-reduce timeout risk"
        elif top_name == "interconnect_degradation" and interconnect_degradation_probability >= 0.42:
            predicted_event = "interconnect degradation risk"
        elif top_name == "residual_memory" and residual_memory_probability >= 0.42:
            predicted_event = "residual GPU memory leak risk"
        elif telemetry_gap_probability >= 0.42:
            predicted_event = "GPU residency with telemetry/process-accounting gap"
        elif residency_watch_probability >= 0.42:
            predicted_event = "GPU residency watch"
        else:
            predicted_event = "workload anomaly watch"

        action_level, decision = workload_action(risk_score)
        if risk_score >= 68 and predicted_event == "rank all-reduce timeout risk":
            decision = "checkpoint if possible, isolate degraded rank or link after validation"
        elif risk_score >= 68 and predicted_event == "interconnect degradation risk":
            decision = "cordon interconnect path, block new distributed jobs, collect NVLink/PCIe evidence"
        actions = [
            recommended_action("INCREASE_WORKLOAD_SAMPLING", "Collect higher-frequency GPU, scheduler and CUDA process telemetry."),
            recommended_action("RECONCILE_CUDA_PIDS", "Compare CUDA PIDs, container IDs and scheduler job IDs."),
            recommended_action("FORBID_AUTOMATIC_PROCESS_KILL", "Orphan worker must be confirmed before a destructive action."),
        ]
        if action_level in {"HIGH", "CRITICAL"}:
            actions.extend(
                [
                    recommended_action("CORDON_GPU", "Prevent new work from landing on the suspect GPU while evidence is collected.", approval=True, target=snapshot.node_id),
                    recommended_action("CHECKPOINT_GUARD", "Protect current training state before restart, rollback or kill."),
                ]
            )
        if action_level == "CRITICAL":
            actions.append(
                recommended_action("REQUEST_HUMAN_APPROVAL", "Human approval required before terminating a process or rolling back training state.", approval=True)
            )
        result = (
            f"{predicted_event}: risk {risk_score:.1f}/100 from R={residency_score:.3f}, "
            f"telemetry_gap={telemetry_gap_probability:.3f}, orphan={orphan_worker_probability:.3f}, "
            f"all_reduce={all_reduce_stall_probability:.3f}."
        )
        formulas = {
            "residency_score": "u * m",
            "p_residency_watch": "sigmoid(5.0 * (R - 0.45))",
            "p_orphan": "sigmoid(-3.0 + 5.5*(R-0.45) + 2.8*scheduler_mismatch + 2.3*process_mismatch + 1.1*memory_not_released - 0.8*legitimate_job_running + 0.9*telemetry_contradiction)",
            "p_memory_leak": "sigmoid(-3.1 + 1.3*m + 2.3*memory_not_released + 1.5*time_after_job_norm + 0.8*scheduler_mismatch)",
            "p_allreduce": "sigmoid(-3.0 + 1.4*step_excess + 2.0*rank_skew + 1.3*nccl + 1.4*interconnect + 0.7*pcie + 0.6*ecc + 0.6*thermal_throttle + 0.5*power_throttle)",
            "p_interconnect": "sigmoid(-2.6 + 2.2*nvlink + 2.0*pcie + 1.3*bandwidth_drop + 1.2*nccl)",
            "p_telemetry_gap": "sigmoid(-2.0 + 3.2*telemetry_contradiction + 0.8*process_accounting_missing + 0.6*stale_telemetry)",
            "risk": "100 * noisy_or(weighted hypothesis probabilities)",
            "confidence": "telemetry quality Q from sample count, contradiction, process accounting and stale telemetry",
        }
        evidence = {
            "u": round(utilization, 3),
            "m": round(memory, 3),
            "R": round(residency_score, 3),
            "scheduler_mismatch": int(scheduler_mismatch),
            "process_mismatch": int(process_mismatch),
            "active_cuda_process_count": active_cuda_process_count,
            "scheduler_registered_process_count": scheduler_registered_process_count,
            "unowned_cuda_process_count": process_mismatch_count,
            "telemetry_contradiction": int(telemetry_contradiction),
            "process_accounting_missing": int(process_accounting_missing),
            "top_hypotheses": [{"name": name, "probability": round(probability, 3)} for name, probability in top_hypotheses],
        }
        return ModulePredictionResult(
            module_id="workload_gpu",
            module_name="Workload-GPU State Reconciliation Agent",
            severity=severity_from_score(risk_score),
            risk_score=risk_score,
            confidence=round(telemetry_quality, 2),
            prediction_horizon_minutes=30,
            result=result,
            predicted_event=predicted_event,
            action_level=action_level,
            dashboard_summary=f"{predicted_event} | {risk_score:.1f}/100 | {action_level} | confidence {telemetry_quality:.2f}",
            metrics=[
                CalculationMetric(name="GPU utilization", value=snapshot.gpu_utilization_percent, unit="%", interpretation="Compute occupancy."),
                CalculationMetric(name="Memory pressure", value=snapshot.memory_used_percent, unit="%", interpretation="Allocated GPU memory fraction."),
                CalculationMetric(name="Residency score", value=round(residency_score, 3), interpretation="GPU utilization ratio x memory pressure."),
                CalculationMetric(name="Scheduler mismatch", value=int(scheduler_mismatch), interpretation="1 when scheduler says idle/failed/unknown while GPU remains active."),
                CalculationMetric(name="Process mismatch", value=int(process_mismatch), interpretation="1 when active CUDA processes are not owned by scheduler jobs."),
                CalculationMetric(name="Active CUDA process count", value=active_cuda_process_count, interpretation="Observed CUDA processes on the GPU or node."),
                CalculationMetric(name="Scheduler registered process count", value=scheduler_registered_process_count, interpretation="CUDA processes that the scheduler believes it owns."),
                CalculationMetric(name="Unowned CUDA process count", value=process_mismatch_count, interpretation="Active CUDA processes not matched to scheduler state."),
                CalculationMetric(name="Legitimate job running", value=int(legitimate_job_running), interpretation="1 when scheduler RUNNING and no mismatch is observed."),
                CalculationMetric(name="Telemetry contradiction", value=int(telemetry_contradiction), interpretation="1 when GPU is active but no CUDA process is visible."),
                CalculationMetric(name="Process accounting missing", value=int(process_accounting_missing), interpretation="1 when PID/process accounting is missing or explicitly not OK."),
                CalculationMetric(name="Telemetry quality", value=round(telemetry_quality, 3), interpretation="Confidence multiplier from sample count and measurement consistency."),
                CalculationMetric(name="Residency watch probability", value=round(residency_watch_probability, 3), interpretation="GPU residency pressure; not an orphan proof by itself."),
                CalculationMetric(name="Orphan worker probability", value=round(orphan_worker_probability, 3), interpretation="Worker-orphan hypothesis gated by scheduler/process mismatch."),
                CalculationMetric(name="Residual memory probability", value=round(residual_memory_probability, 3), interpretation="VRAM remains allocated after job completion or drains too slowly."),
                CalculationMetric(name="All-reduce stall probability", value=round(all_reduce_stall_probability, 3), interpretation="Distributed-training stall hypothesis from ranks, step time, NCCL and link errors."),
                CalculationMetric(name="Interconnect degradation probability", value=round(interconnect_degradation_probability, 3), interpretation="NVLink/PCIe/network degradation hypothesis."),
                CalculationMetric(name="Telemetry gap probability", value=round(telemetry_gap_probability, 3), interpretation="Observation gap when GPU activity and process accounting disagree."),
                CalculationMetric(name="Noisy-OR risk probability", value=round(risk_score / 100, 3), interpretation="Weighted combination of competing hypotheses."),
                CalculationMetric(name="Step time p95 ratio", value=round(step_time_ratio, 3), interpretation="Current step duration divided by rolling p95 step duration."),
                CalculationMetric(name="Rank progress skew norm", value=round(rank_progress_skew_norm, 3), interpretation="Normalized rank progress skew for distributed training."),
                CalculationMetric(name="NCCL warning norm", value=round(nccl_warning_norm, 3), interpretation="NCCL warnings normalized over the recent window."),
                CalculationMetric(name="Interconnect error norm", value=round(interconnect_error_norm, 3), interpretation="NVLink/PCIe/network error rate normalized for scoring."),
                CalculationMetric(name="PCIe replay norm", value=round(pcie_replay_norm, 3), interpretation="PCIe replay counter normalized for interconnect scoring."),
                CalculationMetric(name="NVLink error norm", value=round(nvlink_error_norm, 3), interpretation="NVLink error counter normalized for interconnect scoring."),
                CalculationMetric(name="ECC corrected rate norm", value=round(ecc_corrected_rate_norm, 3), interpretation="Corrected ECC rate normalized for all-reduce risk."),
                CalculationMetric(name="Power throttle flag", value=int(power_throttle_flag), interpretation="1 when power violation time increased in the window."),
                CalculationMetric(name="Thermal throttle flag", value=int(thermal_throttle_flag), interpretation="1 when thermal throttling is observed."),
                CalculationMetric(name="Compute node power", value=round(node_power_watts, 1), unit="W", interpretation="Node/tray power used for workload context; avoids treating multi-GPU node power as single-GPU power."),
                CalculationMetric(name="Utilization slope", value=round(utilization_slope, 3), unit="%/h", interpretation="Observed variation of GPU utilization across input data."),
                CalculationMetric(name="Memory slope", value=round(memory_slope, 3), unit="GB/h", interpretation="Observed variation of allocated GPU memory across input data."),
                CalculationMetric(name="Utilization volatility", value=round(utilization_sigma, 3), unit="%", interpretation="Standard deviation of utilization in the data window."),
            ],
            recommended_decision=decision,
            formula_summary=[
                "u = gpu_utilization_percent / 100; m = gpu_memory_used_gb / gpu_memory_total_gb; R = u x m",
                "p_residency_watch = sigmoid(5.0 x (R - 0.45))",
                "p_orphan = sigmoid(-3.0 + 5.5 x (R - 0.45) + 2.8 x scheduler_mismatch + 2.3 x process_mismatch + 1.1 x memory_not_released - 0.8 x legitimate_job_running + 0.9 x telemetry_contradiction)",
                "p_memory_leak = sigmoid(-3.1 + 1.3 x m + 2.3 x memory_not_released + 1.5 x time_after_job_norm + 0.8 x scheduler_mismatch)",
                "p_allreduce = sigmoid(-3.0 + 1.4 x step_excess + 2.0 x rank_skew + 1.3 x nccl + 1.4 x interconnect + 0.7 x pcie + 0.6 x ecc + 0.6 x thermal_throttle + 0.5 x power_throttle)",
                "p_interconnect = sigmoid(-2.6 + 2.2 x nvlink + 2.0 x pcie + 1.3 x bandwidth_drop + 1.2 x nccl)",
                "p_telemetry_gap = sigmoid(-2.0 + 3.2 x telemetry_contradiction + 0.8 x process_accounting_missing + 0.6 x stale_telemetry)",
                "risk = 100 x (1 - product(1 - weight_i x p_i)) with weights residency=0.45, orphan=0.85, memory=0.75, allreduce=0.85, interconnect=0.70, telemetry_gap=0.40",
                "confidence = clamp(0.95 + 0.05 x min(samples/12,1) - 0.25 x telemetry_contradiction - 0.08 x process_accounting_missing - 0.05 x stale_telemetry, 0.20, 0.98)",
            ],
            evidence=evidence,
            formulas=formulas,
            recommended_actions=actions,
            requires_human_approval=action_level in {"HIGH", "CRITICAL"},
        )

    def thermal_health(
        self,
        snapshot: TelemetrySnapshot,
        elapsed_minutes: int,
        horizon: list[tuple[int, TelemetrySnapshot]],
        trends: DataTrends | None = None,
    ) -> ModulePredictionResult:
        peak_temperature = max(sample.gpu_temperature_celsius for _, sample in horizon)
        thermal_margin = GPU_THERMAL_LIMIT_C - snapshot.gpu_temperature_celsius
        peak_margin = GPU_THERMAL_LIMIT_C - peak_temperature
        gpu_temperature_slope = trends.slope("gpu_temperature_celsius") if trends else 0.0
        radiator_temperature_slope = trends.slope("radiator_temperature_celsius") if trends else 0.0
        radiator_area_m2 = snapshot.radiator_area_m2 or 12.0
        radiator_emissivity = snapshot.radiator_emissivity or 0.85
        radiator_view_factor = snapshot.radiator_view_factor or 0.90
        sun_exposure_factor = snapshot.sun_exposure_factor if snapshot.sun_exposure_factor is not None else 0.4
        heat_rejection_watts = radiator_heat_rejection_w(
            radiator_area_m2,
            radiator_emissivity,
            radiator_view_factor,
            snapshot.radiator_temperature_celsius,
            sun_exposure_factor,
        )
        thermal_deficit_watts = snapshot.gpu_power_watts - heat_rejection_watts
        thermal_resistance = (snapshot.gpu_temperature_celsius - snapshot.radiator_temperature_celsius) / max(snapshot.gpu_power_watts / 1000, 0.1)
        sensor_delta = snapshot.gpu_temperature_celsius - snapshot.board_temperature_celsius
        hotspot_index = sigmoid(
            (snapshot.gpu_temperature_celsius - 86) / 4
            + (snapshot.radiator_temperature_celsius - 58) / 3
            + (sensor_delta - 24) / 5
            + gpu_temperature_slope / 18
        )
        critical_elapsed = first_crossing(horizon, lambda sample: sample.gpu_temperature_celsius >= GPU_CRITICAL_LIMIT_C)
        limit_elapsed = first_crossing(horizon, lambda sample: sample.gpu_temperature_celsius >= GPU_THERMAL_LIMIT_C)
        peak_temperature_pressure = sigmoid((peak_temperature - 89) / 4.5) * 85
        radiative_deficit_pressure = sigmoid(thermal_deficit_watts / 300) * 85
        slope_pressure = sigmoid((gpu_temperature_slope - 4) / 2) * 75
        gpu_temperature_pressure = sigmoid((snapshot.gpu_temperature_celsius - 88) / 4) * 70
        limit_penalty = max(0, -peak_margin) * 8
        risk_score = round(
            clamp(
                max(
                    hotspot_index * 100,
                    gpu_temperature_pressure,
                    radiative_deficit_pressure,
                    slope_pressure,
                    peak_temperature_pressure + limit_penalty,
                ),
                0,
                100,
            ),
            1,
        )
        if critical_elapsed is not None:
            predicted_event = f"critical GPU temperature at {mission_clock(elapsed_minutes + critical_elapsed)}"
        elif limit_elapsed is not None:
            predicted_event = f"thermal limit crossing at {mission_clock(elapsed_minutes + limit_elapsed)}"
        elif thermal_deficit_watts > 0:
            predicted_event = "radiator heat rejection deficit"
        else:
            predicted_event = "no thermal limit crossing in horizon"
        action_level = action_level_from_score(risk_score)
        if risk_score >= 68:
            decision = "set GPU power limit, pause low-priority jobs, and increase checkpoint frequency"
        elif risk_score >= 42:
            decision = "reduce compute burst length and monitor radiator margin"
        else:
            decision = "keep thermal monitoring active"
        actions = [
            recommended_action("MONITOR_RADIATOR_MARGIN", "Track radiative heat rejection against GPU heat load."),
        ]
        if risk_score >= 42:
            actions.append(recommended_action("INCREASE_CHECKPOINT_FREQUENCY", "Protect training state before thermal throttling.", approval=False))
        if risk_score >= 68:
            actions.extend(
                [
                    recommended_action("SET_GPU_POWER_LIMIT", "Radiator heat rejection or peak temperature margin is insufficient.", value="-20%", approval=True, target=snapshot.node_id),
                    recommended_action("PAUSE_LOW_PRIORITY_JOBS", "Free thermal headroom for critical workloads.", approval=True),
                ]
            )
        return ModulePredictionResult(
            module_id="thermal_physical",
            module_name="Thermal / physical health anomaly management",
            severity=severity_from_score(risk_score),
            risk_score=risk_score,
            confidence=0.86,
            prediction_horizon_minutes=PREDICTION_HORIZON_MINUTES,
            result=f"Predicted peak GPU temperature {peak_temperature:.1f}C; current thermal margin {thermal_margin:.1f}C.",
            predicted_event=predicted_event,
            action_level=action_level,
            dashboard_summary=f"{predicted_event} | peak {peak_temperature:.1f}C | {action_level}",
            metrics=[
                CalculationMetric(name="Current GPU temperature", value=snapshot.gpu_temperature_celsius, unit="C", interpretation="Primary heat source temperature."),
                CalculationMetric(name="Predicted peak temperature", value=round(peak_temperature, 1), unit="C", interpretation="Maximum over the forecast horizon."),
                CalculationMetric(name="Thermal resistance", value=round(thermal_resistance, 3), unit="C/kW", interpretation="Observed GPU-radiator delta per kW."),
                CalculationMetric(name="Radiator heat rejection", value=round(heat_rejection_watts, 1), unit="W", interpretation="Stefan-Boltzmann radiative capacity adjusted for view factor and sun exposure."),
                CalculationMetric(name="Thermal deficit", value=round(thermal_deficit_watts, 1), unit="W", interpretation="Positive means GPU heat load exceeds radiator rejection capacity."),
                CalculationMetric(name="Radiator area", value=round(radiator_area_m2, 2), unit="m2", interpretation="Radiative surface area used in the heat rejection estimate."),
                CalculationMetric(name="Radiator emissivity", value=round(radiator_emissivity, 3), interpretation="Surface emissivity used by Stefan-Boltzmann formula."),
                CalculationMetric(name="Radiator view factor", value=round(radiator_view_factor, 3), interpretation="Fraction of radiator view to cold space."),
                CalculationMetric(name="Sun exposure factor", value=round(sun_exposure_factor, 3), interpretation="Solar exposure penalty on effective heat rejection."),
                CalculationMetric(name="Hotspot index", value=round(hotspot_index, 3), interpretation="Logistic hotspot likelihood from GPU, radiator, and board delta."),
                CalculationMetric(name="Peak temperature pressure", value=round(peak_temperature_pressure, 1), unit="/100", interpretation="Smooth risk pressure as forecast peak approaches 89-95C."),
                CalculationMetric(name="Radiative deficit pressure", value=round(radiative_deficit_pressure, 1), unit="/100", interpretation="Risk pressure from positive thermal deficit."),
                CalculationMetric(name="Thermal slope pressure", value=round(slope_pressure, 1), unit="/100", interpretation="Risk pressure from fast temperature rise."),
                CalculationMetric(name="GPU temperature slope", value=round(gpu_temperature_slope, 3), unit="C/h", interpretation="Observed thermal variation from the input data window."),
                CalculationMetric(name="Radiator temperature slope", value=round(radiator_temperature_slope, 3), unit="C/h", interpretation="Observed radiator variation from the input data window."),
            ],
            recommended_decision=decision,
            formula_summary=[
                "thermal_margin = 95C - gpu_temperature_celsius",
                "radiator_heat_rejection_w = emissivity x sigma x area_m2 x view_factor x (radiator_temp_K^4 - space_temp_K^4) x sun_exposure_penalty",
                "thermal_deficit_w = gpu_power_watts - radiator_heat_rejection_w",
                "thermal_resistance = (gpu_temperature_celsius - radiator_temperature_celsius) / (gpu_power_watts / 1000)",
                "hotspot_index = sigmoid((gpu_temp - 86)/4 + (radiator_temp - 58)/3 + (gpu_temp - board_temp - 24)/5 + gpu_temp_slope_per_hour/18)",
                "peak_temperature = max(data-driven predicted gpu_temperature over next 180 minutes)",
                "thermal_risk = max(sigmoid((gpu_temp - 88)/4) x 70, sigmoid(thermal_deficit_w/300) x 85, sigmoid((gpu_temp_slope - 4)/2) x 75, peak_temperature_pressure + limit_penalty)",
            ],
            evidence={
                "gpu_temperature_c": round(snapshot.gpu_temperature_celsius, 2),
                "radiator_temperature_c": round(snapshot.radiator_temperature_celsius, 2),
                "thermal_margin_c": round(thermal_margin, 2),
                "thermal_deficit_w": round(thermal_deficit_watts, 2),
                "radiator_heat_rejection_w": round(heat_rejection_watts, 2),
            },
            formulas={
                "radiator_heat_rejection_w": "epsilon * sigma * area * view_factor * (T_radiator_K^4 - T_space_K^4)",
                "thermal_deficit_w": "gpu_power_watts - radiator_heat_rejection_w",
                "thermal_risk": "max(temperature pressure, radiative deficit pressure, slope pressure, peak forecast pressure)",
            },
            recommended_actions=actions,
            requires_human_approval=risk_score >= 68,
        )

    def orbit_power(
        self,
        snapshot: TelemetrySnapshot,
        elapsed_minutes: int,
        horizon: list[tuple[int, TelemetrySnapshot]],
        trends: DataTrends | None = None,
    ) -> ModulePredictionResult:
        battery_capacity_wh = snapshot.battery_capacity_wh or BATTERY_CAPACITY_WH
        solar_effective_watts = solar_effective_power(snapshot.solar_input_watts, snapshot.solar_incidence_angle_deg)
        spacecraft_base_power = snapshot.spacecraft_base_power_watts
        compute_power = snapshot.compute_power_watts if snapshot.compute_power_watts is not None else (snapshot.compute_node_power_watts or snapshot.gpu_power_watts)
        thermal_control_power = snapshot.thermal_control_power_watts or 0.0
        downlink_power = snapshot.downlink_power_watts or 0.0
        if spacecraft_base_power is None:
            total_draw = snapshot.spacecraft_power_draw_watts
            spacecraft_base_power = max(0.0, total_draw - compute_power - thermal_control_power - downlink_power)
        else:
            total_draw = spacecraft_base_power + compute_power + thermal_control_power + downlink_power
        net_power = solar_effective_watts - total_draw
        modeled_battery_delta_percent_per_hour = (net_power / battery_capacity_wh) * 100
        observed_battery_delta_percent_per_hour = trends.slope("battery_percent") if trends else 0.0
        battery_delta_percent_per_hour = (
            observed_battery_delta_percent_per_hour
            if trends and trends.samples_used >= 2 and trends.window_minutes > 0
            else modeled_battery_delta_percent_per_hour
        )
        power_draw_slope = trends.slope("spacecraft_power_draw_watts") if trends else 0.0
        energy_forecast = []
        soc = snapshot.battery_percent
        last_offset = 0
        for offset, sample in horizon:
            dt_minutes = max(0, offset - last_offset)
            sample_solar = solar_effective_power(sample.solar_input_watts, snapshot.solar_incidence_angle_deg)
            sample_total_draw = (
                (snapshot.spacecraft_base_power_watts or max(0.0, sample.spacecraft_power_draw_watts - compute_power - thermal_control_power - downlink_power))
                + (snapshot.compute_power_watts if snapshot.compute_power_watts is not None else (sample.compute_node_power_watts or sample.gpu_power_watts))
                + thermal_control_power
                + downlink_power
            )
            soc += ((sample_solar - sample_total_draw) * dt_minutes / 60) / battery_capacity_wh * 100
            soc = clamp(soc, 0, 100)
            energy_forecast.append(soc)
            last_offset = offset
        model_min_battery = min(energy_forecast) if energy_forecast else snapshot.battery_percent
        trend_min_battery = min(sample.battery_percent for _, sample in horizon)
        min_battery = min(model_min_battery, trend_min_battery if trends and trends.samples_used >= 2 else model_min_battery)
        eclipse_elapsed = first_crossing(horizon, lambda sample: sample.orbit_phase == OrbitPhase.ECLIPSE)
        radiation_elapsed = first_crossing(horizon, lambda sample: sample.orbit_phase == OrbitPhase.HIGH_RADIATION_ZONE)
        reserve_deficit = max(0, BATTERY_RESERVE_TARGET_PERCENT - min_battery)
        eclipse_eta = snapshot.eclipse_eta_minutes if snapshot.eclipse_eta_minutes is not None else eclipse_elapsed
        radiation_eta = snapshot.radiation_window_eta_minutes if snapshot.radiation_window_eta_minutes is not None else radiation_elapsed
        critical_downlink_eta = snapshot.critical_downlink_eta_minutes
        eclipse_penalty = 18 if eclipse_eta is not None and (float(eclipse_eta) <= 60 or min_battery < BATTERY_RESERVE_TARGET_PERCENT) else 0
        radiation_penalty = 8 if radiation_eta is not None else 0
        draw_penalty = clamp((-battery_delta_percent_per_hour - 8) * 2.5, 0, 25)
        rising_draw_penalty = clamp((power_draw_slope - 220) / 28, 0, 18)
        compute_fraction = compute_power / max(total_draw, 1)
        compute_overcommit_penalty = clamp((compute_fraction - 0.65) * 40, 0, 18)
        cooling_priority_penalty = 10 if thermal_control_power > 0 and min_battery < 45 else 0
        downlink_conflict_penalty = 12 if critical_downlink_eta is not None and critical_downlink_eta <= 45 and min_battery < 50 else 0
        risk_score = round(
            clamp(
                reserve_deficit * 2.4
                + eclipse_penalty
                + radiation_penalty
                + draw_penalty
                + rising_draw_penalty
                + compute_overcommit_penalty
                + cooling_priority_penalty
                + downlink_conflict_penalty,
                0,
                100,
            ),
            1,
        )
        if min_battery < BATTERY_RESERVE_TARGET_PERCENT and eclipse_elapsed is not None:
            predicted_event = f"battery reserve below target before/inside eclipse at {mission_clock(elapsed_minutes + eclipse_elapsed)}"
        elif min_battery < BATTERY_RESERVE_TARGET_PERCENT:
            predicted_event = "battery reserve below target inside forecast horizon"
        elif eclipse_elapsed is not None:
            predicted_event = f"eclipse at {mission_clock(elapsed_minutes + eclipse_elapsed)} with reserve above target"
        elif radiation_elapsed is not None:
            predicted_event = f"radiation-aware scheduling window at {mission_clock(elapsed_minutes + radiation_elapsed)}"
        else:
            predicted_event = "no power reserve violation in horizon"
        action_level = action_level_from_score(risk_score)
        if risk_score >= 68:
            decision = "reserve power for cooling and downlink; throttle non-critical training"
        elif risk_score >= 42:
            decision = "reduce compute power budget and delay optional jobs"
        else:
            decision = "power budget acceptable"
        actions = [
            recommended_action("TRACK_POWER_BUDGET", "Continuously compare solar effective power against compute, cooling and downlink draw."),
        ]
        if risk_score >= 42:
            actions.append(recommended_action("REDUCE_COMPUTE_POWER_BUDGET", "Protect battery reserve for cooling, recovery and communications.", approval=True))
        if risk_score >= 68:
            actions.extend(
                [
                    recommended_action("THROTTLE_NON_CRITICAL_TRAINING", "Reserve energy for cooling and downlink.", approval=True),
                    recommended_action("DELAY_OPTIONAL_JOBS", "Avoid compute overcommit before eclipse or critical contact."),
                ]
            )
        return ModulePredictionResult(
            module_id="orbit_power",
            module_name="Orbit-aware power and radiation-aware workload management",
            severity=severity_from_score(risk_score),
            risk_score=risk_score,
            confidence=0.83,
            prediction_horizon_minutes=PREDICTION_HORIZON_MINUTES,
            result=f"Net power {net_power:.0f}W; predicted minimum battery {min_battery:.1f}% over 180 minutes.",
            predicted_event=predicted_event,
            action_level=action_level,
            dashboard_summary=f"{predicted_event} | min battery {min_battery:.1f}% | {action_level}",
            metrics=[
                CalculationMetric(name="Solar effective power", value=round(solar_effective_watts, 1), unit="W", interpretation="Solar input corrected for incidence angle and degradation."),
                CalculationMetric(name="Total draw", value=round(total_draw, 1), unit="W", interpretation="Base spacecraft + compute + cooling + downlink power."),
                CalculationMetric(name="Base power", value=round(spacecraft_base_power, 1), unit="W", interpretation="Non-compute spacecraft load."),
                CalculationMetric(name="Compute power", value=round(compute_power, 1), unit="W", interpretation="GPU/node compute allocation."),
                CalculationMetric(name="Thermal control power", value=round(thermal_control_power, 1), unit="W", interpretation="Cooling and heat transport allocation."),
                CalculationMetric(name="Downlink power", value=round(downlink_power, 1), unit="W", interpretation="Communications allocation."),
                CalculationMetric(name="Net power", value=round(net_power, 1), unit="W", interpretation="Effective solar generation minus total draw."),
                CalculationMetric(name="Battery slope", value=round(battery_delta_percent_per_hour, 2), unit="%/h", interpretation="Observed battery variation when history is available, otherwise power-model estimate."),
                CalculationMetric(name="Modeled battery slope", value=round(modeled_battery_delta_percent_per_hour, 2), unit="%/h", interpretation="Power-balance estimate using net watts / battery capacity."),
                CalculationMetric(name="Observed battery slope", value=round(observed_battery_delta_percent_per_hour, 2), unit="%/h", interpretation="Battery variation directly measured from the input data."),
                CalculationMetric(name="Power draw slope", value=round(power_draw_slope, 2), unit="W/h", interpretation="Observed spacecraft draw variation from the input data."),
                CalculationMetric(name="Predicted minimum battery", value=round(min_battery, 1), unit="%", interpretation="Minimum forecast battery reserve."),
                CalculationMetric(name="Battery capacity", value=round(battery_capacity_wh, 1), unit="Wh", interpretation="Capacity used for energy trajectory integration."),
                CalculationMetric(name="Compute fraction", value=round(compute_fraction, 3), interpretation="Share of draw allocated to compute."),
                CalculationMetric(name="Compute overcommit penalty", value=round(compute_overcommit_penalty, 1), unit="/100", interpretation="Penalty when compute dominates available power budget."),
                CalculationMetric(name="Downlink conflict penalty", value=round(downlink_conflict_penalty, 1), unit="/100", interpretation="Penalty when a critical contact conflicts with low battery reserve."),
                CalculationMetric(name="Next eclipse", value=mission_clock(elapsed_minutes + eclipse_elapsed) if eclipse_elapsed is not None else "none", interpretation="First eclipse sample inside forecast horizon."),
                CalculationMetric(name="Next radiation pass", value=mission_clock(elapsed_minutes + radiation_elapsed) if radiation_elapsed is not None else "none", interpretation="First high-radiation sample inside forecast horizon."),
            ],
            recommended_decision=decision,
            formula_summary=[
                "solar_effective_watts = solar_input_watts x max(0, cos(incidence_angle)) x (1 - degradation)",
                "total_draw_watts = spacecraft_base_power + compute_power + thermal_control_power + downlink_power",
                "net_power_watts = solar_effective_watts - total_draw_watts",
                "modeled_battery_delta_percent_per_hour = net_power_watts / battery_capacity_wh x 100",
                "observed_battery_delta_percent_per_hour = delta(battery_percent) / delta(time_hours)",
                "forecast_battery integrates net power over the forecast horizon and clamps state of charge to [0,100]",
                "reserve_deficit = max(0, 35% - min(predicted_battery_percent))",
                "risk = reserve_deficit x 2.4 + eclipse_penalty + radiation_penalty + draw_penalty + rising_draw_penalty + compute_overcommit_penalty + cooling_priority_penalty + downlink_conflict_penalty",
            ],
            evidence={
                "solar_effective_watts": round(solar_effective_watts, 2),
                "total_draw_watts": round(total_draw, 2),
                "net_power_watts": round(net_power, 2),
                "min_battery_percent": round(min_battery, 2),
                "reserve_deficit_percent": round(reserve_deficit, 2),
                "compute_fraction": round(compute_fraction, 3),
            },
            formulas={
                "solar_effective_power": "panel_power * cos(incidence_angle) * (1 - degradation)",
                "battery_delta_percent_per_hour": "net_power_w / battery_capacity_wh * 100",
                "power_risk": "reserve deficit + eclipse/radiation/draw/compute/cooling/downlink penalties",
            },
            recommended_actions=actions,
            requires_human_approval=risk_score >= 42,
        )

    def radiation_integrity(
        self,
        snapshot: TelemetrySnapshot,
        horizon: list[tuple[int, TelemetrySnapshot]],
        trends: DataTrends | None = None,
    ) -> ModulePredictionResult:
        peak_dose = max(sample.radiation_dose_rate for _, sample in horizon)
        peak_corrected = max(sample.ecc_corrected_errors for _, sample in horizon)
        future_uncorrected = max(sample.ecc_uncorrected_errors for _, sample in horizon)
        dose_slope = trends.slope("radiation_dose_rate") if trends else 0.0
        corrected_ecc_slope = trends.slope("ecc_corrected_errors") if trends else 0.0
        corrected_delta = snapshot.ecc_corrected_delta if snapshot.ecc_corrected_delta is not None else max(0, int(round(peak_corrected - snapshot.ecc_corrected_errors)))
        uncorrected_delta = snapshot.ecc_uncorrected_delta if snapshot.ecc_uncorrected_delta is not None else future_uncorrected
        checkpoint_penalty = {
            CheckpointStatus.TRUSTED: 0.0,
            CheckpointStatus.UNKNOWN: 0.25,
            CheckpointStatus.SUSPECT: 0.65,
            CheckpointStatus.CORRUPTED: 1.0,
        }.get(snapshot.checkpoint_latest_status, 0.35)
        checkpoint_hash_verified = True if snapshot.checkpoint_hash_verified is None else snapshot.checkpoint_hash_verified
        hash_penalty = 0.0 if checkpoint_hash_verified else 0.3
        canary_eval_score = snapshot.canary_eval_score if snapshot.canary_eval_score is not None else 0.98
        canary_penalty = max(0.0, 0.98 - canary_eval_score) * 2.0
        saa_penalty = 0.5 if snapshot.south_atlantic_anomaly_flag else 0.0
        solar_particle_event_index = snapshot.solar_particle_event_index or 0.0
        event_lambda = (
            peak_dose * 0.34
            + max(corrected_delta, max(0.0, corrected_ecc_slope)) * 0.018
            + max(0, dose_slope) * 0.08
            + max(0, corrected_ecc_slope) * 0.012
            + uncorrected_delta * 2.3
            + saa_penalty
            + solar_particle_event_index * 0.7
            + checkpoint_penalty
        )
        bitflip_probability = 1 - math.exp(-event_lambda)
        checkpoint_trust_score = clamp(
            100
            - bitflip_probability * 72
            - uncorrected_delta * 28
            - checkpoint_penalty * 40
            - hash_penalty * 30
            - canary_penalty * 25,
            0,
            100,
        )
        risk_score = round(100 - checkpoint_trust_score, 1)
        if risk_score >= 86:
            predicted_event = "rollback to last trusted checkpoint required"
        elif risk_score >= 68:
            predicted_event = "suspect checkpoint validation required"
        elif risk_score >= 42:
            predicted_event = "radiation/ECC integrity watch elevated"
        else:
            predicted_event = "integrity watch"
        action_level = action_level_from_score(risk_score)
        if risk_score >= 86:
            decision = "rollback to last trusted checkpoint and quarantine current checkpoint"
        elif risk_score >= 68:
            decision = "mark checkpoint suspect and run canary validation"
        elif risk_score >= 42:
            decision = "send hashes and ECC logs; increase validation frequency"
        else:
            decision = "integrity watch"
        actions = [
            recommended_action("SEND_HASHES_AND_ECC_LOGS", "Ground needs compact integrity evidence."),
            recommended_action("RUN_CANARY_VALIDATION", "Validate training state against a trusted canary set."),
        ]
        if risk_score >= 68:
            actions.append(recommended_action("MARK_CHECKPOINT_SUSPECT", "Checkpoint trust is below operational threshold.", approval=False, target=snapshot.checkpoint_latest_id))
        if risk_score >= 86:
            actions.append(recommended_action("ROLLBACK_TO_LAST_TRUSTED_CHECKPOINT", "Current checkpoint integrity is not trustworthy.", approval=True))
        return ModulePredictionResult(
            module_id="radiation_integrity",
            module_name="Radiation / bit-flip / training integrity management",
            severity=severity_from_score(risk_score),
            risk_score=risk_score,
            confidence=0.92 if uncorrected_delta else 0.82,
            prediction_horizon_minutes=PREDICTION_HORIZON_MINUTES,
            result=f"Bit-flip event probability {bitflip_probability:.3f}; checkpoint trust score {checkpoint_trust_score:.1f}/100.",
            predicted_event=predicted_event,
            action_level=action_level,
            dashboard_summary=f"{predicted_event} | trust {checkpoint_trust_score:.1f}/100 | {action_level}",
            metrics=[
                CalculationMetric(name="Peak dose rate", value=round(peak_dose, 3), interpretation="Maximum radiation dose proxy in horizon."),
                CalculationMetric(name="Peak corrected ECC", value=peak_corrected, interpretation="Maximum corrected memory errors in horizon."),
                CalculationMetric(name="Corrected ECC delta", value=corrected_delta, interpretation="Recent corrected ECC increase used as observed corruption pressure."),
                CalculationMetric(name="Uncorrected ECC delta", value=uncorrected_delta, interpretation="Non-correctable memory event indicator."),
                CalculationMetric(name="Checkpoint trust score", value=round(checkpoint_trust_score, 1), unit="/100", interpretation="Remaining trust after ECC/radiation penalty."),
                CalculationMetric(name="Checkpoint penalty", value=round(checkpoint_penalty, 3), interpretation="Penalty from checkpoint status TRUSTED/UNKNOWN/SUSPECT/CORRUPTED."),
                CalculationMetric(name="Hash penalty", value=round(hash_penalty, 3), interpretation="Penalty when latest checkpoint hash is not verified."),
                CalculationMetric(name="Canary penalty", value=round(canary_penalty, 3), interpretation="Penalty from validation score below 0.98."),
                CalculationMetric(name="SAA flag", value=int(bool(snapshot.south_atlantic_anomaly_flag)), interpretation="South Atlantic Anomaly / high-radiation region indicator."),
                CalculationMetric(name="Solar particle event index", value=round(solar_particle_event_index, 3), interpretation="Solar particle event pressure term."),
                CalculationMetric(name="Dose rate slope", value=round(dose_slope, 3), unit="/h", interpretation="Observed radiation dose variation from the input data."),
                CalculationMetric(name="Corrected ECC slope", value=round(corrected_ecc_slope, 3), unit="errors/h", interpretation="Observed corrected ECC variation from the input data."),
            ],
            recommended_decision=decision,
            formula_summary=[
                "lambda = peak_dose_rate x 0.34 + ecc_corrected_rate x 0.018 + positive_dose_slope x 0.08 + positive_ecc_slope x 0.012 + ecc_uncorrected_delta x 2.3 + SAA_flag x 0.5 + solar_particle_event_index x 0.7 + checkpoint_penalty",
                "bitflip_probability = 1 - exp(-lambda)",
                "checkpoint_penalty = TRUSTED:0, UNKNOWN:0.25, SUSPECT:0.65, CORRUPTED:1.0",
                "hash_penalty = 0 if checkpoint_hash_verified else 0.3",
                "canary_penalty = max(0, 0.98 - canary_eval_score) x 2.0",
                "checkpoint_trust = 100 - bitflip_probability x 72 - ecc_uncorrected_delta x 28 - checkpoint_penalty x 40 - hash_penalty x 30 - canary_penalty x 25",
                "radiation_risk = 100 - checkpoint_trust",
            ],
            evidence={
                "peak_dose_rate": round(peak_dose, 3),
                "bitflip_probability": round(bitflip_probability, 3),
                "checkpoint_trust_score": round(checkpoint_trust_score, 1),
                "checkpoint_hash_verified": checkpoint_hash_verified,
                "canary_eval_score": round(canary_eval_score, 3),
                "uncorrected_ecc_delta": uncorrected_delta,
            },
            formulas={
                "poisson_lambda": "dose + ECC + orbital radiation flags + checkpoint penalty",
                "bitflip_probability": "1 - exp(-lambda)",
                "checkpoint_trust": "100 minus bitflip, ECC, checkpoint, hash and canary penalties",
            },
            recommended_actions=actions,
            requires_human_approval=risk_score >= 86,
        )

    def checkpoint_downlink(
        self,
        snapshot: TelemetrySnapshot,
        elapsed_minutes: int,
        horizon: list[tuple[int, TelemetrySnapshot]],
        trends: DataTrends | None = None,
    ) -> ModulePredictionResult:
        current_capacity = downlink_capacity_gb(snapshot.downlink_available_mbps, snapshot.downlink_window_seconds)
        future_contact = [(elapsed, sample) for elapsed, sample in horizon if sample.downlink_window_seconds > 0]
        future_capacity_from_horizon = sum(downlink_capacity_gb(sample.downlink_available_mbps, sample.downlink_window_seconds) for _, sample in future_contact)
        future_capacity_from_windows = 0.0
        for window in snapshot.future_contact_windows or []:
            future_capacity_from_windows += downlink_capacity_gb(float(window.get("mbps", 0)), float(window.get("seconds", 0)))
        future_capacity = max(future_capacity_from_horizon, future_capacity_from_windows)
        capacity_slope = trends.slope("downlink_available_mbps") if trends else 0.0
        storage_slope = trends.slope("local_storage_free_gb") if trends else 0.0
        checkpoint_full_size_gb = snapshot.checkpoint_full_size_gb or snapshot.checkpoint_latest_size_gb
        checkpoint_delta_size_gb = snapshot.checkpoint_delta_size_gb or DOWNLINK_PAYLOADS_GB["delta_checkpoint"]
        compression_ratio = snapshot.compression_ratio_estimate or 1.0
        effective_full_size_gb = checkpoint_full_size_gb * compression_ratio
        payloads = [
            {"name": "manifest", "size_gb": snapshot.manifest_size_gb or DOWNLINK_PAYLOADS_GB["manifest"], "priority": 100, "required": True},
            {"name": "hashes", "size_gb": snapshot.hashes_size_gb or DOWNLINK_PAYLOADS_GB["hashes"], "priority": 95, "required": True},
            {"name": "ecc_logs", "size_gb": snapshot.ecc_logs_size_gb or DOWNLINK_PAYLOADS_GB["ecc_logs"], "priority": 85, "required": False},
            {"name": "thermal_logs", "size_gb": snapshot.thermal_logs_size_gb or DOWNLINK_PAYLOADS_GB["thermal_logs"], "priority": 70, "required": False},
            {"name": "workload_logs", "size_gb": snapshot.workload_logs_size_gb or DOWNLINK_PAYLOADS_GB["workload_logs"], "priority": 65, "required": False},
            {"name": "delta_checkpoint", "size_gb": checkpoint_delta_size_gb, "priority": 60, "required": False},
            {"name": "full_checkpoint", "size_gb": effective_full_size_gb, "priority": 40, "required": False},
        ]
        selected_payload_objects, remaining = select_payloads(payloads, current_capacity)
        selected_payloads = [payload["name"] for payload in selected_payload_objects]
        minimal_evidence_size = sum(float(payload["size_gb"]) for payload in payloads if payload["name"] in {"manifest", "hashes", "ecc_logs", "thermal_logs"})
        full_fit_ratio = current_capacity / max(effective_full_size_gb, 0.1)
        forecast_fit_ratio = future_capacity / max(effective_full_size_gb, 0.1)
        storage_risk = sigmoid((90 - snapshot.local_storage_free_gb) / 14)
        capacity_gap = max(0, effective_full_size_gb - current_capacity)
        worsening_storage_penalty = clamp((-storage_slope - 8) * 1.4, 0, 20)
        ack_penalty = 12 if snapshot.ground_ack_status.value != "ACKED" else 0
        bit_error_penalty = clamp((snapshot.bit_error_rate or 0.0) * 1_000_000, 0, 12)
        risk_score = round(
            clamp(
                max(0, 1 - min(full_fit_ratio, 1)) * 65
                + storage_risk * 35
                + ack_penalty
                + worsening_storage_penalty
                + bit_error_penalty,
                0,
                100,
            ),
            1,
        )
        next_contact = mission_clock(elapsed_minutes + future_contact[0][0]) if future_contact else "none"
        chunk_size_gb = 1.0
        num_chunks = math.ceil(effective_full_size_gb / chunk_size_gb)
        chunks_to_send_now = int(current_capacity // chunk_size_gb)
        if current_capacity >= effective_full_size_gb:
            predicted_event = "full checkpoint fits current contact"
        elif full_fit_ratio < 0.1:
            predicted_event = "send compact recovery evidence only"
        elif "delta_checkpoint" in selected_payloads:
            predicted_event = "send manifest, hashes, logs, and delta checkpoint"
        elif current_capacity >= minimal_evidence_size:
            predicted_event = "send manifest, hashes, and logs only"
        else:
            predicted_event = "contact window too small for full recovery evidence"
        action_level = action_level_from_score(risk_score)
        if full_fit_ratio < 0.1:
            decision = "send manifest, hashes, ECC logs and thermal/workload logs only"
        elif full_fit_ratio < 1:
            decision = "send delta checkpoint and schedule full checkpoint over future contacts"
        else:
            decision = "send full checkpoint"
        if not selected_payloads:
            decision = "wait for next contact and preserve local checkpoint"
        actions = [
            recommended_action("DO_NOT_DELETE_LOCAL_CHECKPOINT", "Local checkpoint must remain until ground ACK is confirmed."),
            recommended_action("SEND_SELECTED_PAYLOADS", "Transmit highest-priority recovery evidence that fits current capacity.", value=", ".join(selected_payloads) or "none"),
        ]
        if full_fit_ratio < 1:
            actions.append(recommended_action("SCHEDULE_FUTURE_FULL_CHECKPOINT", "Full checkpoint does not fit current contact window."))
        if snapshot.ground_ack_status.value != "ACKED":
            actions.append(recommended_action("WAIT_FOR_GROUND_ACK", "Do not free local storage or delete checkpoint before ground confirmation."))
        return ModulePredictionResult(
            module_id="checkpoint_downlink",
            module_name="Checkpoint / downlink / recovery management",
            severity=severity_from_score(risk_score),
            risk_score=risk_score,
            confidence=0.92,
            prediction_horizon_minutes=PREDICTION_HORIZON_MINUTES,
            result=f"Current downlink capacity {current_capacity:.2f}GB; full checkpoint gap {capacity_gap:.2f}GB.",
            predicted_event=predicted_event,
            action_level=action_level,
            dashboard_summary=f"{predicted_event} | capacity {current_capacity:.2f}GB | {action_level}",
            metrics=[
                CalculationMetric(name="Current contact capacity", value=round(current_capacity, 2), unit="GB", interpretation="Mbps x seconds / 8192."),
                CalculationMetric(name="Checkpoint size", value=round(effective_full_size_gb, 2), unit="GB", interpretation="Full recovery object size after optional compression estimate."),
                CalculationMetric(name="Raw checkpoint size", value=round(checkpoint_full_size_gb, 2), unit="GB", interpretation="Full checkpoint size before compression estimate."),
                CalculationMetric(name="Delta checkpoint size", value=round(checkpoint_delta_size_gb, 2), unit="GB", interpretation="Delta checkpoint object size."),
                CalculationMetric(name="Full fit ratio", value=round(full_fit_ratio, 3), interpretation="Capacity divided by full checkpoint size."),
                CalculationMetric(name="Forecast fit ratio", value=round(forecast_fit_ratio, 3), interpretation="Forecast contact capacity divided by full checkpoint size."),
                CalculationMetric(name="Forecast contact capacity", value=round(future_capacity, 2), unit="GB", interpretation="Sum of contacts in the forecast horizon."),
                CalculationMetric(name="Selected payloads", value=", ".join(selected_payloads) or "none", interpretation="Payloads chosen by priority under current capacity."),
                CalculationMetric(name="Remaining contact capacity", value=round(remaining, 2), unit="GB", interpretation="Capacity left after selected payloads."),
                CalculationMetric(name="Minimal evidence bundle", value=round(minimal_evidence_size, 2), unit="GB", interpretation="Manifest + hashes + ECC logs + thermal logs."),
                CalculationMetric(name="Checkpoint chunks", value=num_chunks, interpretation="Number of 1GB chunks needed for the full checkpoint."),
                CalculationMetric(name="Chunks sendable now", value=chunks_to_send_now, interpretation="Number of full 1GB chunks that fit current contact."),
                CalculationMetric(name="Do not delete local checkpoint until ACK", value="true", interpretation="Safety invariant for recovery management."),
                CalculationMetric(name="Ground ACK status", value=snapshot.ground_ack_status.value, interpretation="Ground confirmation state."),
                CalculationMetric(name="Bit error penalty", value=round(bit_error_penalty, 2), unit="/100", interpretation="Penalty from estimated downlink bit error rate."),
                CalculationMetric(name="Next contact", value=next_contact, interpretation="Next predicted downlink window."),
                CalculationMetric(name="Downlink Mbps slope", value=round(capacity_slope, 3), unit="Mbps/h", interpretation="Observed downlink rate variation from the input data."),
                CalculationMetric(name="Local storage slope", value=round(storage_slope, 3), unit="GB/h", interpretation="Observed storage variation from the input data."),
            ],
            recommended_decision=decision,
            formula_summary=[
                "downlink_capacity_gb = downlink_available_mbps x downlink_window_seconds / 8192",
                "full_fit_ratio = current_capacity_gb / checkpoint_size_gb",
                "forecast_fit_ratio = sum(future_contact_capacity_gb) / checkpoint_size_gb",
                "payload priority = manifest -> hashes -> ECC logs -> thermal logs -> workload logs -> delta checkpoint -> full checkpoint",
                "selected_payloads = greedy priority selection under current capacity",
                "num_chunks = ceil(full_checkpoint_size_gb / 1GB); chunks_to_send_now = floor(current_capacity_gb / 1GB)",
                "risk = missing full checkpoint capacity + local storage risk + pending ground ACK penalty + worsening_storage_penalty + bit_error_penalty",
            ],
            evidence={
                "current_capacity_gb": round(current_capacity, 3),
                "full_checkpoint_size_gb": round(effective_full_size_gb, 3),
                "full_fit_ratio": round(full_fit_ratio, 4),
                "forecast_capacity_gb": round(future_capacity, 3),
                "selected_payloads": selected_payloads,
                "do_not_delete_local_checkpoint_until_ground_ack": True,
            },
            formulas={
                "downlink_capacity_gb": "mbps * seconds / 8192",
                "payload_selection": "greedy priority selection under capacity",
                "chunking": "ceil(checkpoint_size_gb / 1GB)",
                "downlink_risk": "capacity gap + storage + ACK + bit error penalties",
            },
            recommended_actions=actions,
            requires_human_approval=risk_score >= 68,
        )
