from __future__ import annotations

from ..models import (
    CheckpointStatus,
    GroundAckStatus,
    MissionActionType,
    MissionPatch,
    Severity,
    TelemetrySnapshot,
    ValidationResult,
)


class MissionPatchValidator:
    def validate(
        self,
        patch: MissionPatch,
        snapshot: TelemetrySnapshot,
        highest_thermal_severity: Severity = Severity.INFO,
        human_approved: bool = False,
    ) -> ValidationResult:
        blocked: list[str] = []
        warnings: list[str] = []
        requires_human = patch.requires_human_approval
        capacity = snapshot.downlink_capacity_gb

        for action in patch.actions:
            if action.action_type == MissionActionType.RESUME_JOB and snapshot.ecc_uncorrected_errors > 0 and not human_approved:
                blocked.append("Cannot resume a job on a GPU with uncorrected ECC errors without human approval.")
            if action.action_type == MissionActionType.ROLLBACK_TO_LAST_TRUSTED_CHECKPOINT:
                requires_human = True
            if action.action_type == MissionActionType.DELAY_FULL_CHECKPOINT_DOWNLINK:
                warnings.append("Full checkpoint downlink delayed until trust and bandwidth improve.")
            if action.action_type == MissionActionType.PRIORITIZE_DOWNLINK_DELTA_CHECKPOINT and snapshot.checkpoint_latest_size_gb > capacity:
                warnings.append("Delta checkpoint may still exceed available downlink; send manifest and hashes first.")

        if snapshot.ground_ack_status != GroundAckStatus.ACKED:
            warnings.append("Do not delete or overwrite the last trusted checkpoint until ground ACK is received.")
        if highest_thermal_severity in {Severity.HIGH, Severity.CRITICAL}:
            warnings.append("GPU power must not be increased while thermal severity is high or critical.")
        if snapshot.downlink_window_seconds and snapshot.checkpoint_latest_size_gb > capacity:
            warnings.append("Full checkpoint does not fit in the current downlink window.")
        if snapshot.checkpoint_latest_status == CheckpointStatus.SUSPECT:
            warnings.append("A suspect checkpoint cannot be marked trusted without validation evidence.")
        if snapshot.ecc_uncorrected_errors > 0 and not human_approved:
            requires_human = True

        return ValidationResult(
            is_valid=not blocked,
            blocked_reasons=blocked,
            warnings=warnings,
            requires_human_approval=requires_human,
        )
