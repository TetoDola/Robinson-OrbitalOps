from __future__ import annotations

from ..agents.commander_agent import CommanderAgent
from ..database import OrbitOpsDatabase
from ..models import ApprovalEvent, MissionPatch, PatchStatus, Severity
from ..validators.mission_patch_validator import MissionPatchValidator
from .telemetry_service import TelemetryService


class PatchService:
    def __init__(self, database: OrbitOpsDatabase, telemetry: TelemetryService) -> None:
        self.database = database
        self.telemetry = telemetry
        self.commander = CommanderAgent()
        self.validator = MissionPatchValidator()
        self._latest_patch: MissionPatch | None = None
        self._approved_patch_ids: set[str] = set()

    def latest(self) -> MissionPatch | None:
        return self._latest_patch

    def propose(self) -> MissionPatch:
        snapshot = self.telemetry.latest()
        findings = self.telemetry.findings()
        patch = self.commander.propose_patch(snapshot, findings)
        highest_thermal = self._highest_thermal_severity(findings)
        patch.validation_result = self.validator.validate(patch, snapshot, highest_thermal)
        self._latest_patch = patch
        self._record_patch(patch)
        return patch

    def approve(self, patch_id: str) -> MissionPatch:
        patch = self._require_patch(patch_id)
        patch.status = PatchStatus.APPROVED
        patch.validation_result = self.validator.validate(
            patch,
            self.telemetry.latest(),
            self._highest_thermal_severity(self.telemetry.findings()),
            human_approved=True,
        )
        self._approved_patch_ids.add(patch.patch_id)
        self._record_patch(patch)
        self._record_approval(patch, "approved")
        return patch

    def reject(self, patch_id: str) -> MissionPatch:
        patch = self._require_patch(patch_id)
        patch.status = PatchStatus.REJECTED
        self._record_patch(patch)
        self._record_approval(patch, "rejected")
        return patch

    def execute(self, patch_id: str) -> MissionPatch:
        patch = self._require_patch(patch_id)
        human_approved = patch.patch_id in self._approved_patch_ids
        patch.validation_result = self.validator.validate(
            patch,
            self.telemetry.latest(),
            self._highest_thermal_severity(self.telemetry.findings()),
            human_approved=human_approved,
        )
        if patch.validation_result.is_valid and (
            not patch.validation_result.requires_human_approval or human_approved
        ):
            patch.status = PatchStatus.EXECUTED
        else:
            patch.status = PatchStatus.FAILED
        self._record_patch(patch)
        return patch

    def _require_patch(self, patch_id: str) -> MissionPatch:
        if not self._latest_patch or self._latest_patch.patch_id != patch_id:
            raise KeyError(patch_id)
        return self._latest_patch

    def _record_patch(self, patch: MissionPatch) -> None:
        self.database.insert_model(
            "mission_patches",
            patch,
            {"patch_id": patch.patch_id, "created_at": patch.created_at, "status": patch.status.value},
        )

    def _record_approval(self, patch: MissionPatch, decision: str) -> None:
        event = ApprovalEvent(patch_id=patch.patch_id, decision=decision)
        self.database.insert_model(
            "approval_events",
            event,
            {
                "event_id": event.event_id,
                "created_at": event.timestamp,
                "patch_id": event.patch_id,
                "decision": event.decision,
            },
        )

    @staticmethod
    def _highest_thermal_severity(findings) -> Severity:
        thermal = [finding.severity for finding in findings if "Thermal" in finding.agent_name]
        if any(severity == Severity.CRITICAL for severity in thermal):
            return Severity.CRITICAL
        if any(severity == Severity.HIGH for severity in thermal):
            return Severity.HIGH
        if any(severity == Severity.MEDIUM for severity in thermal):
            return Severity.MEDIUM
        return Severity.INFO
