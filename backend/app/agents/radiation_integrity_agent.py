from __future__ import annotations

from ..models import CheckpointStatus, OrbitPhase, Severity, TelemetrySnapshot
from .base import BaseAgent


class RadiationIntegrityAgent(BaseAgent):
    name = "Radiation / Integrity Agent"

    def analyze(self, snapshot: TelemetrySnapshot):
        findings = []
        if snapshot.ecc_uncorrected_errors > 0:
            findings.append(self.finding(
                Severity.CRITICAL,
                0.98,
                "Uncorrected ECC error threatens training integrity",
                "A non-correctable memory event means the latest training state cannot be trusted without validation.",
                [
                    f"Uncorrected ECC errors: {snapshot.ecc_uncorrected_errors}.",
                    f"Checkpoint status: {snapshot.checkpoint_latest_status.value}.",
                    f"Radiation dose rate: {snapshot.radiation_dose_rate:.2f}.",
                ],
                ["Mark latest checkpoint suspect", "Run canary evaluation", "Rollback to last trusted checkpoint", "Request human review"],
                [snapshot.node_id, snapshot.checkpoint_latest_id],
                True,
            ))
        elif snapshot.ecc_corrected_errors > 25:
            findings.append(self.finding(
                Severity.HIGH,
                0.88,
                "Corrected ECC count is rising",
                "Radiation risk is no longer theoretical; memory correction is active.",
                [f"Corrected ECC errors: {snapshot.ecc_corrected_errors}."],
                ["Run canary evaluation", "Prioritize ECC logs", "Increase checkpoint scrutiny"],
                [snapshot.node_id],
            ))
        if snapshot.orbit_phase == OrbitPhase.HIGH_RADIATION_ZONE and snapshot.ecc_corrected_errors > 10:
            findings.append(self.finding(
                Severity.HIGH,
                0.86,
                "High-radiation pass overlaps ECC activity",
                "The orbital environment is increasing integrity risk during training.",
                [f"Orbit phase {snapshot.orbit_phase.value}", f"Dose rate {snapshot.radiation_dose_rate:.2f}"],
                ["Quarantine output artifact", "Rerun suspect batch/window", "Cordon GPU after ECC event"],
                [snapshot.node_id, snapshot.job_id],
            ))
        if snapshot.checkpoint_latest_status in {CheckpointStatus.UNKNOWN, CheckpointStatus.SUSPECT} and snapshot.ecc_corrected_errors > 0:
            findings.append(self.finding(
                Severity.HIGH,
                0.82,
                "Checkpoint trust cannot be assumed",
                "The latest checkpoint was created near an ECC/radiation event.",
                [f"Checkpoint {snapshot.checkpoint_latest_id} is {snapshot.checkpoint_latest_status.value}."],
                ["Mark checkpoint suspect", "Prioritize hashes", "Delay trusted recovery use"],
                [snapshot.checkpoint_latest_id],
                True,
            ))
        if not findings:
            findings.append(self.finding(
                Severity.INFO,
                0.84,
                "Integrity posture nominal",
                "ECC and radiation indicators are within expected mission range.",
                [f"Corrected ECC {snapshot.ecc_corrected_errors}", f"Uncorrected ECC {snapshot.ecc_uncorrected_errors}"],
                ["Continue monitoring"],
                [snapshot.node_id],
            ))
        return findings
