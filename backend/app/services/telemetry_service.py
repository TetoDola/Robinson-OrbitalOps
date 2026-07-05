from __future__ import annotations

from ..agents.checkpoint_downlink_agent import CheckpointDownlinkRecoveryAgent
from ..agents.orbit_power_agent import OrbitPowerAgent
from ..agents.radiation_integrity_agent import RadiationIntegrityAgent
from ..agents.thermal_health_agent import ThermalHealthAgent
from ..agents.workload_gpu_agent import WorkloadGpuAgent
from ..database import OrbitOpsDatabase
from ..models import (
    AgentFinding,
    ComputeNodeStatus,
    DashboardState,
    GpuStatus,
    SatelliteTopology,
    SEVERITY_RANK,
    Severity,
    TelemetrySnapshot,
)
from ..simulator.telemetry_simulator import TelemetrySimulator
from ..science.calculation_modules import ScientificPredictionEngine
from ..science.types import ScientificAssessment
from .incident_service import IncidentService


class TelemetryService:
    def __init__(self, database: OrbitOpsDatabase, simulator: TelemetrySimulator) -> None:
        self.database = database
        self.simulator = simulator
        self.agents = [
            WorkloadGpuAgent(),
            ThermalHealthAgent(),
            OrbitPowerAgent(),
            RadiationIntegrityAgent(),
            CheckpointDownlinkRecoveryAgent(),
        ]
        self.incident_service = IncidentService(database)
        self.science_engine = ScientificPredictionEngine()
        self._last_findings: list[AgentFinding] = []
        self._record_snapshot(self.simulator.latest())
        self.run_agents()

    def latest(self) -> TelemetrySnapshot:
        return self.simulator.latest()

    def history(self) -> list[TelemetrySnapshot]:
        return self.simulator.history()

    def sql_history(self, limit: int = 96) -> list[TelemetrySnapshot]:
        payloads = self.database.list_payloads_ascending("telemetry_snapshots", limit=limit)
        snapshots = []
        for payload in payloads:
            try:
                snapshots.append(TelemetrySnapshot.model_validate(payload))
            except ValueError:
                continue
        return snapshots

    def start(self) -> TelemetrySnapshot:
        snapshot = self.simulator.start()
        self._record_snapshot(snapshot)
        self.run_agents()
        return snapshot

    def stop(self) -> TelemetrySnapshot:
        return self.simulator.stop()

    def reset(self) -> TelemetrySnapshot:
        self.database.reset_demo()
        snapshot = self.simulator.reset()
        self._record_snapshot(snapshot)
        self.run_agents()
        return snapshot

    def advance_if_running(self) -> TelemetrySnapshot:
        if self.simulator.running:
            snapshot = self.simulator.advance()
            self._record_snapshot(snapshot)
            self.run_agents()
        return self.simulator.latest()

    def step(self) -> TelemetrySnapshot:
        snapshot = self.simulator.advance()
        self._record_snapshot(snapshot)
        self.run_agents()
        return snapshot

    def run_agents(self) -> list[AgentFinding]:
        snapshot = self.latest()
        findings = [finding for agent in self.agents for finding in agent.analyze(snapshot)]
        self._last_findings = findings
        for finding in findings:
            self.database.insert_model(
                "agent_findings",
                finding,
                {
                    "created_at": snapshot.timestamp,
                    "agent_name": finding.agent_name,
                    "severity": finding.severity.value,
                },
            )
        self.incident_service.sync_from_findings(findings)
        return findings

    def findings(self) -> list[AgentFinding]:
        if not self._last_findings:
            return self.run_agents()
        return self._last_findings

    def highest_severity(self) -> Severity:
        return max((finding.severity for finding in self.findings()), key=lambda severity: SEVERITY_RANK[severity])

    def downlink_queue(self) -> list[dict[str, str | int]]:
        snapshot = self.latest()
        capacity = snapshot.downlink_capacity_gb
        items = [
            ("manifest", "Checkpoint manifest", 1, "READY"),
            ("hashes", "Integrity hashes", 2, "READY"),
            ("ecc_logs", "ECC/radiation logs", 1, "READY"),
            ("thermal_logs", "Thermal evidence", 1, "READY"),
            ("delta_checkpoint", "Delta checkpoint", 18, "WAITING"),
            ("full_checkpoint", "Full checkpoint", int(snapshot.checkpoint_latest_size_gb), "BLOCKED"),
        ]
        queue = []
        used = 0
        for item_id, label, size_gb, status in items:
            projected = used + size_gb
            if status != "BLOCKED" and projected <= capacity:
                effective_status = "QUEUED"
                used = projected
            elif item_id == "full_checkpoint":
                effective_status = "BLOCKED"
            else:
                effective_status = "WAITING"
            queue.append({"id": item_id, "label": label, "size_gb": size_gb, "status": effective_status})
        return queue

    def scientific_assessment(self) -> ScientificAssessment:
        sql_history = self.sql_history()
        latest = sql_history[-1] if sql_history else self.latest()
        return self.science_engine.assess(latest, self.simulator.elapsed_minutes, sql_history or self.history())

    def ingest_science_samples(self, samples: list[TelemetrySnapshot], elapsed_minutes: int = 0) -> ScientificAssessment:
        for sample in samples:
            self.database.insert_model(
                "telemetry_snapshots",
                sample,
                {"created_at": sample.timestamp, "mission_id": sample.mission_id},
            )
        return self.science_engine.assess(samples[-1], elapsed_minutes, samples)

    def satellite_topology(self) -> SatelliteTopology:
        snapshot = self.latest()
        nodes: list[ComputeNodeStatus] = []
        node_ids = ["OGPU-AURORA-7", "OGPU-AURORA-8", "OGPU-BOREAL-3", "OGPU-VEGA-2"]
        roles = ["primary-training", "checkpoint-recovery", "inference-standby", "thermal-spare"]
        degraded_gpus = 0
        active_gpus = 0
        total_utilization = 0.0

        for node_index, node_id in enumerate(node_ids):
            node_factor = 1 - 0.11 * node_index
            is_primary = node_index == 0
            gpus: list[GpuStatus] = []
            node_power = 0.0
            node_temp = snapshot.board_temperature_celsius - 2 * node_index
            node_severity = Severity.INFO
            node_active_gpus = 0

            for gpu_index in range(4):
                gpu_id = f"{node_id}-GPU-{gpu_index}"
                primary_heat = 1 if is_primary else 0.35
                utilization = max(0, min(99, snapshot.gpu_utilization_percent * node_factor - gpu_index * 4 + (3 if gpu_index == 0 else 0)))
                memory_used = max(0, min(snapshot.gpu_memory_total_gb / 4, (snapshot.gpu_memory_used_gb / 4) * node_factor - gpu_index * 1.6))
                temperature = max(38, snapshot.gpu_temperature_celsius - node_index * 5 - gpu_index * 1.8 + primary_heat * 2)
                power = max(120, (snapshot.gpu_power_watts / 4) * node_factor - gpu_index * 35)
                ecc_corrected = max(0, int(snapshot.ecc_corrected_errors * (1 if is_primary and gpu_index == 0 else 0.16 * node_factor)))
                ecc_uncorrected = 1 if is_primary and gpu_index == 0 and snapshot.ecc_uncorrected_errors else 0
                if ecc_uncorrected or temperature > 95:
                    severity = Severity.CRITICAL
                    state = "quarantine"
                elif temperature > 86 or ecc_corrected > 12:
                    severity = Severity.HIGH
                    state = "degraded"
                elif utilization < 8 and snapshot.scheduler_state.value == "RUNNING":
                    severity = Severity.MEDIUM
                    state = "watch"
                else:
                    severity = Severity.INFO
                    state = "active" if utilization > 15 else "standby"

                if utilization > 15:
                    active_gpus += 1
                    node_active_gpus += 1
                if severity in {Severity.HIGH, Severity.CRITICAL}:
                    degraded_gpus += 1
                if SEVERITY_RANK[severity] > SEVERITY_RANK[node_severity]:
                    node_severity = severity
                total_utilization += utilization
                node_power += power

                gpus.append(
                    GpuStatus(
                        gpu_id=gpu_id,
                        utilization_percent=round(utilization, 1),
                        memory_used_gb=round(memory_used, 1),
                        memory_total_gb=round(snapshot.gpu_memory_total_gb / 4, 1),
                        temperature_celsius=round(temperature, 1),
                        power_watts=round(power, 1),
                        ecc_corrected_errors=ecc_corrected,
                        ecc_uncorrected_errors=ecc_uncorrected,
                        state=state,
                        severity=severity,
                    )
                )

            if node_severity == Severity.CRITICAL:
                status = "quarantine"
            elif node_severity == Severity.HIGH:
                status = "degraded"
            elif node_active_gpus:
                status = "active"
            else:
                status = "standby"

            nodes.append(
                ComputeNodeStatus(
                    node_id=node_id,
                    role=roles[node_index],
                    status=status,
                    severity=node_severity,
                    gpu_count=len(gpus),
                    active_job_id=snapshot.job_id if is_primary else None,
                    board_temperature_celsius=round(node_temp, 1),
                    power_watts=round(node_power, 1),
                    gpus=gpus,
                )
            )

        total_gpus = sum(node.gpu_count for node in nodes)
        return SatelliteTopology(
            satellite_id="SAT-ORBITOPS-01",
            bus_status="nominal" if snapshot.battery_percent > 30 else "power-constrained",
            compute_nodes=nodes,
            total_nodes=len(nodes),
            total_gpus=total_gpus,
            active_gpus=active_gpus,
            degraded_gpus=degraded_gpus,
            aggregate_gpu_utilization_percent=round(total_utilization / total_gpus, 1),
        )

    def dashboard_state(self, latest_patch=None) -> DashboardState:
        findings = self.findings()
        incidents = self.incident_service.list_incidents()
        return DashboardState(
            latest_snapshot=self.latest(),
            history=self.history(),
            findings=findings,
            incidents=incidents,
            latest_patch=latest_patch,
            simulator_running=self.simulator.running,
            timeline_step=self.simulator.index,
            simulated_elapsed_minutes=self.simulator.elapsed_minutes,
            mission_clock=self.simulator.mission_clock,
            orbit_number=self.simulator.orbit_number,
            orbit_fraction=self.simulator.orbit_fraction,
            simulation_speed="1 live tick = 15 simulated minutes; full 24h pass = 96 ticks",
            calculation_notes=self.simulator.notes(),
            satellite_topology=self.satellite_topology(),
            downlink_queue=self.downlink_queue(),
            overall_risk=self.highest_severity(),
        )

    def _record_snapshot(self, snapshot: TelemetrySnapshot) -> None:
        self.database.insert_model(
            "telemetry_snapshots",
            snapshot,
            {"created_at": snapshot.timestamp, "mission_id": snapshot.mission_id},
        )
