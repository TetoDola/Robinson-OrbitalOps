from __future__ import annotations

from ..models import SchedulerState, Severity, TelemetrySnapshot
from .base import BaseAgent


class WorkloadGpuAgent(BaseAgent):
    name = "Workload / GPU Agent"

    def analyze(self, snapshot: TelemetrySnapshot):
        findings = []
        mem_pct = snapshot.memory_used_percent
        if snapshot.scheduler_state == SchedulerState.IDLE and snapshot.gpu_utilization_percent > 70:
            findings.append(self.finding(
                Severity.HIGH,
                0.94,
                "Scheduler/GPU truth mismatch",
                "The scheduler reports the node idle while the GPU is actively consuming compute.",
                [
                    f"Scheduler says IDLE but GPU utilization is {snapshot.gpu_utilization_percent:.0f}%.",
                    f"GPU power draw is {snapshot.gpu_power_watts:.0f}W.",
                    f"Memory remains {mem_pct:.0f}% allocated.",
                ],
                ["Inspect process table", "Cordon GPU", "Preserve workload logs"],
                [snapshot.node_id, snapshot.job_id],
                True,
            ))
        elif snapshot.scheduler_state == SchedulerState.RUNNING and snapshot.gpu_utilization_percent < 5 and mem_pct > 50:
            findings.append(self.finding(
                Severity.MEDIUM,
                0.72,
                "Possible stuck worker",
                "Memory remains allocated while utilization has collapsed.",
                [f"GPU utilization {snapshot.gpu_utilization_percent:.0f}%", f"Memory used {mem_pct:.0f}%"],
                ["Pause job", "Collect worker logs", "Run canary batch"],
                [snapshot.node_id, snapshot.job_id],
            ))
        elif snapshot.scheduler_state == SchedulerState.IDLE and mem_pct > 20:
            findings.append(self.finding(
                Severity.MEDIUM,
                0.7,
                "Residual GPU allocation after scheduler idle",
                "The node may contain orphaned training state.",
                [f"Memory used {mem_pct:.0f}% while scheduler is IDLE."],
                ["Preserve logs", "Cordon node until process table is inspected"],
                [snapshot.node_id],
            ))
        if not findings:
            findings.append(self.finding(
                Severity.INFO,
                0.88,
                "Workload state nominal",
                "Scheduler and GPU telemetry are aligned.",
                [f"{snapshot.scheduler_state.value} with {snapshot.gpu_utilization_percent:.0f}% GPU utilization."],
                ["Continue monitoring"],
                [snapshot.node_id],
            ))
        return findings
