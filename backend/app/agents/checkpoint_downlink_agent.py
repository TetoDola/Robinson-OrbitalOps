from __future__ import annotations

from ..models import CheckpointStatus, GroundAckStatus, Severity, TelemetrySnapshot
from .base import BaseAgent


class CheckpointDownlinkRecoveryAgent(BaseAgent):
    name = "Checkpoint / Downlink / Recovery Agent"

    def analyze(self, snapshot: TelemetrySnapshot):
        findings = []
        capacity = snapshot.downlink_capacity_gb
        if snapshot.downlink_window_seconds and snapshot.checkpoint_latest_size_gb > capacity:
            findings.append(self.finding(
                Severity.HIGH,
                0.9,
                "Full checkpoint cannot fit in current downlink window",
                "The downlink window should send manifest, hashes, and logs before any full checkpoint transfer.",
                [
                    f"Checkpoint size {snapshot.checkpoint_latest_size_gb:.0f}GB.",
                    f"Window capacity {capacity:.2f}GB.",
                ],
                ["Prioritize manifest", "Prioritize hashes", "Prioritize ECC logs", "Delay full checkpoint downlink"],
                ["downlink", snapshot.checkpoint_latest_id],
            ))
        if snapshot.checkpoint_latest_status in {CheckpointStatus.SUSPECT, CheckpointStatus.CORRUPTED}:
            findings.append(self.finding(
                Severity.HIGH if snapshot.checkpoint_latest_status == CheckpointStatus.SUSPECT else Severity.CRITICAL,
                0.93,
                "Latest checkpoint is not trusted recovery state",
                "Do not treat the newest checkpoint as a safe rollback target until validation succeeds.",
                [f"{snapshot.checkpoint_latest_id} is {snapshot.checkpoint_latest_status.value}."],
                ["Keep last trusted checkpoint", "Send hashes first", "Run canary validation"],
                [snapshot.checkpoint_latest_id],
                True,
            ))
        if snapshot.local_storage_free_gb < 90:
            findings.append(self.finding(
                Severity.HIGH,
                0.84,
                "Local storage margin is low",
                "Cleanup is risky until ground acknowledges the last trusted checkpoint.",
                [f"Local free storage {snapshot.local_storage_free_gb:.0f}GB.", f"Ground ACK {snapshot.ground_ack_status.value}."],
                ["Preserve last trusted checkpoint", "Wait for ground acknowledgment", "Prioritize delta checkpoint"],
                [snapshot.node_id, "local-storage"],
            ))
        if snapshot.ground_ack_status == GroundAckStatus.PENDING:
            findings.append(self.finding(
                Severity.MEDIUM,
                0.78,
                "Ground acknowledgment pending",
                "Local recovery data must be preserved until ground confirms receipt.",
                [f"Ground ACK is {snapshot.ground_ack_status.value}."],
                ["Do not delete local copy", "Send manifest/hashes first"],
                [snapshot.checkpoint_latest_id],
            ))
        if not findings:
            findings.append(self.finding(
                Severity.INFO,
                0.86,
                "Checkpoint and downlink posture nominal",
                "Recovery state and communications margin are acceptable.",
                [f"Checkpoint {snapshot.checkpoint_latest_status.value}", f"Downlink capacity {capacity:.2f}GB"],
                ["Continue monitoring"],
                ["downlink"],
            ))
        return findings
