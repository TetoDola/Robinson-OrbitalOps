from __future__ import annotations

from ..models import Severity, TelemetrySnapshot
from .base import BaseAgent


class ThermalHealthAgent(BaseAgent):
    name = "Thermal / Physical Health Agent"

    def analyze(self, snapshot: TelemetrySnapshot):
        findings = []
        severity = None
        if snapshot.gpu_temperature_celsius > 95:
            severity = Severity.CRITICAL
        elif snapshot.gpu_temperature_celsius > 85:
            severity = Severity.HIGH
        elif snapshot.radiator_temperature_celsius > 55 and snapshot.gpu_power_watts > 3500:
            severity = Severity.MEDIUM
        if severity:
            findings.append(self.finding(
                severity,
                0.91 if severity == Severity.CRITICAL else 0.82,
                "Thermal headroom is collapsing",
                "GPU and radiator temperatures show a hotspot while the workload is still power intensive.",
                [
                    f"GPU temperature is {snapshot.gpu_temperature_celsius:.0f}C.",
                    f"Radiator temperature is {snapshot.radiator_temperature_celsius:.0f}C.",
                    f"GPU power draw is {snapshot.gpu_power_watts:.0f}W.",
                ],
                ["Lower GPU power limit", "Enter cooldown mode", "Increase checkpoint frequency", "Preserve thermal evidence"],
                [snapshot.node_id],
                severity == Severity.CRITICAL,
            ))
        if abs(snapshot.gpu_temperature_celsius - snapshot.board_temperature_celsius) > 28:
            findings.append(self.finding(
                Severity.MEDIUM,
                0.67,
                "Thermal sensor divergence",
                "GPU and board temperatures diverge enough to suggest conduction or sensor drift.",
                [f"GPU {snapshot.gpu_temperature_celsius:.0f}C vs board {snapshot.board_temperature_celsius:.0f}C."],
                ["Preserve thermal evidence", "Avoid scheduling on hot node"],
                [snapshot.node_id],
            ))
        if not findings:
            findings.append(self.finding(
                Severity.INFO,
                0.86,
                "Thermal envelope stable",
                "Temperature telemetry remains inside mission limits.",
                [f"GPU temperature {snapshot.gpu_temperature_celsius:.0f}C."],
                ["Continue monitoring"],
                [snapshot.node_id],
            ))
        return findings
