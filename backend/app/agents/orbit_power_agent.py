from __future__ import annotations

from ..models import OrbitPhase, Severity, TelemetrySnapshot
from .base import BaseAgent


class OrbitPowerAgent(BaseAgent):
    name = "Orbit-Aware Power Agent"

    def analyze(self, snapshot: TelemetrySnapshot):
        findings = []
        if snapshot.battery_percent < 20:
            findings.append(self.finding(
                Severity.CRITICAL,
                0.95,
                "Battery margin is mission critical",
                "The spacecraft is below safe compute margin and must reserve power for survival, cooling, and recovery.",
                [f"Battery is {snapshot.battery_percent:.0f}%.", f"Orbit phase is {snapshot.orbit_phase.value}."],
                ["Lower GPU power", "Pause non-critical training", "Reserve power for cooling/downlink"],
                [snapshot.node_id, "spacecraft-power-bus"],
                True,
            ))
        elif snapshot.orbit_phase == OrbitPhase.ECLIPSE and snapshot.battery_percent < 35:
            findings.append(self.finding(
                Severity.HIGH,
                0.9,
                "Eclipse power derating required",
                "Compute, cooling, and downlink are competing while battery margin is low.",
                [
                    f"Battery is {snapshot.battery_percent:.0f}% during ECLIPSE.",
                    f"Solar input is {snapshot.solar_input_watts:.0f}W.",
                    f"Spacecraft draw is {snapshot.spacecraft_power_draw_watts:.0f}W.",
                ],
                ["Reduce GPU power", "Checkpoint before derating", "Reserve power for recovery actions"],
                [snapshot.node_id, "spacecraft-power-bus"],
            ))
        elif snapshot.solar_input_watts < 2000 and snapshot.spacecraft_power_draw_watts > 5200:
            findings.append(self.finding(
                Severity.MEDIUM,
                0.78,
                "Solar input drop conflicts with compute draw",
                "Power generation dropped while the workload remains expensive.",
                [f"Solar input {snapshot.solar_input_watts:.0f}W", f"Draw {snapshot.spacecraft_power_draw_watts:.0f}W"],
                ["Reduce GPU power", "Delay non-critical training"],
                [snapshot.node_id],
            ))
        if snapshot.downlink_window_seconds and snapshot.battery_percent < 40:
            findings.append(self.finding(
                Severity.MEDIUM,
                0.73,
                "Downlink and compute are competing for low battery",
                "The active downlink window is useful, but full transfer would compete with recovery power.",
                [f"Downlink window {snapshot.downlink_window_seconds}s", f"Battery {snapshot.battery_percent:.0f}%"],
                ["Prioritize manifest/hashes", "Delay full checkpoint downlink"],
                ["downlink", "spacecraft-power-bus"],
            ))
        if not findings:
            findings.append(self.finding(
                Severity.INFO,
                0.85,
                "Power posture nominal",
                "Orbit phase and battery margin support current compute state.",
                [f"Battery {snapshot.battery_percent:.0f}%", f"Solar input {snapshot.solar_input_watts:.0f}W"],
                ["Continue monitoring"],
                ["spacecraft-power-bus"],
            ))
        return findings
