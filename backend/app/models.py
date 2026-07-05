from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class OrbitPhase(str, Enum):
    SUNLIGHT = "SUNLIGHT"
    ECLIPSE = "ECLIPSE"
    TERMINATOR = "TERMINATOR"
    HIGH_RADIATION_ZONE = "HIGH_RADIATION_ZONE"


class SchedulerState(str, Enum):
    RUNNING = "RUNNING"
    IDLE = "IDLE"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class CheckpointStatus(str, Enum):
    TRUSTED = "TRUSTED"
    SUSPECT = "SUSPECT"
    CORRUPTED = "CORRUPTED"
    UNKNOWN = "UNKNOWN"


class GroundAckStatus(str, Enum):
    ACKED = "ACKED"
    PENDING = "PENDING"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class Severity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PatchStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class MissionActionType(str, Enum):
    PAUSE_JOB = "PAUSE_JOB"
    RESUME_JOB = "RESUME_JOB"
    LOWER_GPU_POWER_LIMIT = "LOWER_GPU_POWER_LIMIT"
    CORDON_GPU = "CORDON_GPU"
    INCREASE_CHECKPOINT_FREQUENCY = "INCREASE_CHECKPOINT_FREQUENCY"
    MARK_CHECKPOINT_SUSPECT = "MARK_CHECKPOINT_SUSPECT"
    ROLLBACK_TO_LAST_TRUSTED_CHECKPOINT = "ROLLBACK_TO_LAST_TRUSTED_CHECKPOINT"
    RERUN_SUSPECT_BATCH = "RERUN_SUSPECT_BATCH"
    PRIORITIZE_DOWNLINK_MANIFEST = "PRIORITIZE_DOWNLINK_MANIFEST"
    PRIORITIZE_DOWNLINK_HASHES = "PRIORITIZE_DOWNLINK_HASHES"
    PRIORITIZE_DOWNLINK_DELTA_CHECKPOINT = "PRIORITIZE_DOWNLINK_DELTA_CHECKPOINT"
    DELAY_FULL_CHECKPOINT_DOWNLINK = "DELAY_FULL_CHECKPOINT_DOWNLINK"
    ENTER_COOLDOWN_MODE = "ENTER_COOLDOWN_MODE"
    REQUEST_HUMAN_REVIEW = "REQUEST_HUMAN_REVIEW"


SEVERITY_RANK = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


class TelemetrySnapshot(BaseModel):
    timestamp: str
    mission_id: str
    orbit_phase: OrbitPhase
    node_id: str
    job_id: str
    scheduler_state: SchedulerState
    gpu_utilization_percent: float
    gpu_memory_used_gb: float
    gpu_memory_total_gb: float
    gpu_power_watts: float
    gpu_temperature_celsius: float
    board_temperature_celsius: float
    radiator_temperature_celsius: float
    battery_percent: float
    solar_input_watts: float
    spacecraft_power_draw_watts: float
    downlink_available_mbps: float
    downlink_window_seconds: int
    ecc_corrected_errors: int
    ecc_uncorrected_errors: int
    radiation_dose_rate: float
    checkpoint_latest_id: str
    checkpoint_latest_status: CheckpointStatus
    checkpoint_latest_size_gb: float
    local_storage_free_gb: float
    ground_ack_status: GroundAckStatus
    compute_node_power_watts: float | None = None
    active_cuda_process_count: int | None = None
    scheduler_registered_process_count: int | None = None
    active_cuda_processes_not_in_scheduler: int | None = None
    time_since_last_job_end_seconds: float | None = None
    memory_release_delta_gb_per_min: float | None = None
    rank_progress_skew: float | None = None
    current_step_duration_seconds: float | None = None
    rolling_p95_step_duration_seconds: float | None = None
    nccl_warning_count: int | None = None
    interconnect_error_rate: float | None = None
    power_violation_time_delta_seconds: float | None = None
    xid_error_count: int | None = None
    hbm_temperature_c: float | None = None
    coolant_loop_temperature_c: float | None = None
    radiator_area_m2: float | None = None
    radiator_emissivity: float | None = None
    radiator_view_factor: float | None = None
    sun_exposure_factor: float | None = None
    spacecraft_base_power_watts: float | None = None
    compute_power_watts: float | None = None
    thermal_control_power_watts: float | None = None
    downlink_power_watts: float | None = None
    battery_capacity_wh: float | None = None
    solar_incidence_angle_deg: float | None = None
    eclipse_eta_minutes: float | None = None
    radiation_window_eta_minutes: float | None = None
    critical_downlink_eta_minutes: float | None = None
    pcie_replay_count: int | None = None
    nvlink_error_count: int | None = None
    process_accounting_status: str | None = None
    bandwidth_drop_percent: float | None = None
    stale_telemetry_seconds: float | None = None
    thermal_throttle_flag: bool | None = None
    radiation_dose_accumulated: float | None = None
    orbital_latitude_deg: float | None = None
    altitude_km: float | None = None
    south_atlantic_anomaly_flag: bool | None = None
    solar_particle_event_index: float | None = None
    ecc_corrected_delta: int | None = None
    ecc_uncorrected_delta: int | None = None
    checkpoint_hash_verified: bool | None = None
    canary_eval_score: float | None = None
    last_trusted_checkpoint_age_minutes: float | None = None
    future_contact_windows: list[dict[str, Any]] | None = None
    checkpoint_full_size_gb: float | None = None
    checkpoint_delta_size_gb: float | None = None
    manifest_size_gb: float | None = None
    hashes_size_gb: float | None = None
    ecc_logs_size_gb: float | None = None
    thermal_logs_size_gb: float | None = None
    workload_logs_size_gb: float | None = None
    bit_error_rate: float | None = None
    compression_ratio_estimate: float | None = None

    @property
    def memory_used_percent(self) -> float:
        return round((self.gpu_memory_used_gb / max(self.gpu_memory_total_gb, 0.1)) * 100, 1)

    @property
    def downlink_capacity_gb(self) -> float:
        return round((self.downlink_available_mbps * self.downlink_window_seconds) / 8192, 2)


class AgentFinding(BaseModel):
    agent_name: str
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    title: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    affected_resources: list[str] = Field(default_factory=list)
    requires_human_approval: bool = False


class MissionAction(BaseModel):
    action_type: MissionActionType
    target: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str


class ValidationResult(BaseModel):
    is_valid: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_human_approval: bool = False


class MissionPatch(BaseModel):
    patch_id: str = Field(default_factory=lambda: f"PATCH-{str(uuid4())[:8].upper()}")
    created_at: str = Field(default_factory=utc_now)
    status: PatchStatus = PatchStatus.PROPOSED
    summary: str
    rationale: str
    actions: list[MissionAction]
    risk_reduction_score: float = Field(ge=0, le=100)
    operational_cost_score: float = Field(ge=0, le=100)
    requires_human_approval: bool
    validation_result: ValidationResult | None = None


class Incident(BaseModel):
    incident_id: str = Field(default_factory=lambda: f"INC-{str(uuid4())[:8].upper()}")
    timestamp: str = Field(default_factory=utc_now)
    severity: Severity
    title: str
    summary: str
    source_agents: list[str] = Field(default_factory=list)


class ApprovalEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"EVT-{str(uuid4())[:8].upper()}")
    timestamp: str = Field(default_factory=utc_now)
    patch_id: str
    decision: str
    operator: str = "mission-operator"


class GpuStatus(BaseModel):
    gpu_id: str
    utilization_percent: float
    memory_used_gb: float
    memory_total_gb: float
    temperature_celsius: float
    power_watts: float
    ecc_corrected_errors: int
    ecc_uncorrected_errors: int
    state: str
    severity: Severity


class ComputeNodeStatus(BaseModel):
    node_id: str
    role: str
    status: str
    severity: Severity
    gpu_count: int
    active_job_id: str | None
    board_temperature_celsius: float
    power_watts: float
    gpus: list[GpuStatus]


class SatelliteTopology(BaseModel):
    satellite_id: str
    bus_status: str
    compute_nodes: list[ComputeNodeStatus]
    total_nodes: int
    total_gpus: int
    active_gpus: int
    degraded_gpus: int
    aggregate_gpu_utilization_percent: float


class DashboardState(BaseModel):
    latest_snapshot: TelemetrySnapshot
    history: list[TelemetrySnapshot]
    findings: list[AgentFinding]
    incidents: list[Incident]
    latest_patch: MissionPatch | None
    simulator_running: bool
    timeline_step: int
    simulated_elapsed_minutes: int
    mission_clock: str
    orbit_number: int
    orbit_fraction: float
    simulation_speed: str
    calculation_notes: list[str]
    satellite_topology: SatelliteTopology
    downlink_queue: list[dict[str, Any]]
    overall_risk: Severity


Modality = Literal["telemetry", "log", "image", "topology", "report", "calculation", "thermal", "operator_message"]
AgentSource = Literal["local", "crusoe", "fallback"]


class MultimodalObservation(BaseModel):
    observation_id: str = Field(default_factory=lambda: f"OBS-{str(uuid4())[:8].upper()}")
    timestamp: str = Field(default_factory=utc_now)
    modality: Modality
    summary: str
    content: str | dict[str, Any] | None = None
    mime_type: str | None = None
    uri: str | None = None


class OperatorFeedback(BaseModel):
    feedback_id: str = Field(default_factory=lambda: f"FDBK-{str(uuid4())[:8].upper()}")
    timestamp: str = Field(default_factory=utc_now)
    message: str
    accepted_action_ids: list[str] = Field(default_factory=list)
    rejected_action_ids: list[str] = Field(default_factory=list)
    risk_tolerance: Literal["conservative", "balanced", "aggressive"] = "balanced"
    policy_notes: list[str] = Field(default_factory=list)


class RandomSimulationConfig(BaseModel):
    seed: int | None = None
    scenario: Literal[
        "mixed",
        "nominal",
        "thermal_ramp",
        "radiation_pass",
        "downlink_congestion",
        "scheduler_mismatch",
        "power_eclipse",
    ] = "mixed"
    intensity: float = Field(default=0.72, ge=0, le=1)
    noise: float = Field(default=0.18, ge=0, le=1)
    step_minutes: int = Field(default=5, ge=1, le=30)
    start_elapsed_minutes: int | None = Field(default=None, ge=0)
    auto_advance: bool = True


class PredictiveAgentRequest(BaseModel):
    message: str | None = None
    observations: list[MultimodalObservation] = Field(default_factory=list)
    feedback: OperatorFeedback | None = None
    force_crusoe: bool = False


class ActionApprovalRequest(BaseModel):
    action_id: str
    decision: Literal["approved", "rejected"]
    notes: str | None = None


class AgentTrainingExample(BaseModel):
    example_id: str = Field(default_factory=lambda: f"TRN-{str(uuid4())[:8].upper()}")
    timestamp: str = Field(default_factory=utc_now)
    input_summary: dict[str, Any]
    expected_output: dict[str, Any]
    label_source: Literal["simulation", "operator", "incident_replay"] = "simulation"


class PredictiveAgentResult(BaseModel):
    result_id: str = Field(default_factory=lambda: f"PRED-{str(uuid4())[:8].upper()}")
    timestamp: str = Field(default_factory=utc_now)
    source: AgentSource
    model: str
    mission_id: str
    mode: Literal["stream", "deep_analysis", "chat"] = "stream"
    multimodal_inputs: list[MultimodalObservation] = Field(default_factory=list)
    overall_risk_score: float = Field(ge=0, le=100)
    severity: Severity
    primary_driver: str
    predicted_event: str
    eta_minutes: float | None = None
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    reasoning_trace: list[str] = Field(default_factory=list)
    recommended_actions: list[dict[str, Any]] = Field(default_factory=list)
    operator_questions: list[str] = Field(default_factory=list)
    adaptation_notes: list[str] = Field(default_factory=list)
    module_results: list[dict[str, Any]] = Field(default_factory=list)
    performance_metrics: dict[str, Any] = Field(default_factory=dict)
    response_text: str | None = None


class AgentMemoryState(BaseModel):
    feedback_count: int = 0
    risk_tolerance: Literal["conservative", "balanced", "aggressive"] = "balanced"
    policy_notes: list[str] = Field(default_factory=list)
    accepted_action_ids: list[str] = Field(default_factory=list)
    rejected_action_ids: list[str] = Field(default_factory=list)
    recent_predictions: list[PredictiveAgentResult] = Field(default_factory=list)
    training_examples: list[AgentTrainingExample] = Field(default_factory=list)
