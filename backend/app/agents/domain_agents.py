"""Remaining mock domain agents for Phase 4."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.constants import DEMO_SCENARIO_RUN_ID, StreamName
from app.db.models import AgentFinding, AgentStatus, WorldStateCurrent
from app.db.session import session_context
from app.services.agent_status import emit_agent_status
from app.services.event_bus import publish_stream_event


def build_workload_finding(state: dict[str, Any]) -> dict[str, Any] | None:
    node_a = next(node for node in state["nodes"] if node["id"] == "node-a")
    if node_a["gpu_util"] > 85 and node_a.get("rank_lag", 0) > 0.05:
        return _finding(
            "workload_agent",
            "ORANGE",
            0.82,
            ["node-a", "llm-train-042"],
            "Rank lag detected while GPU utilization remains high.",
            ["Node A GPU utilization is 94%", "Rank lag exceeds 5%", "Training job is still running"],
            "Training throughput may stall before eclipse.",
            ["snapshot_evidence", "run_health_check", "pause_job"],
            "workload_rank_lag",
        )
    return None


def build_thermal_finding(state: dict[str, Any]) -> dict[str, Any] | None:
    if state["thermal"]["highest_temp_c"] >= 88:
        return _finding(
            "thermal_physical_agent",
            "RED",
            0.9,
            ["node-c"],
            "Node C hotspot is above safe thermal threshold.",
            ["Node C is hottest asset", "Cooling status is degraded", "Structure-borne vibration is elevated"],
            "Node C should not receive critical workloads.",
            ["mark_node_suspect", "set_gpu_power_limit", "run_health_check"],
            "thermal_node_c_hotspot",
        )
    return None


def build_radiation_finding(state: dict[str, Any]) -> dict[str, Any] | None:
    if state["radiation"]["ecc_errors_last_5min"] > 900:
        return _finding(
            "radiation_integrity_agent",
            "RED",
            0.86,
            ["node-b", "ckpt-184900"],
            "ECC errors spiked during a suspect checkpoint window.",
            ["ECC count exceeds 900", "Xid event observed", "Latest checkpoint is suspect"],
            "Latest checkpoint may contain corrupted training state.",
            ["mark_checkpoint_suspect", "cordon_node", "run_health_check"],
            "radiation_checkpoint_integrity",
        )
    return None


def build_checkpoint_downlink_finding(state: dict[str, Any]) -> dict[str, Any] | None:
    if state["downlink"]["capacity_gb"] < 180:
        return _finding(
            "checkpoint_downlink_agent",
            "YELLOW",
            0.84,
            ["ckpt-184900", "ground-link"],
            "Full checkpoint exceeds current downlink capacity.",
            ["Full checkpoint is 180 GB", "Current downlink capacity is 22 GB", "Delta checkpoint can fit"],
            "Ground recovery should receive manifest, hashes, logs, and delta first.",
            ["transfer_priority"],
            "downlink_checkpoint_fit",
        )
    return None


def build_vibration_finding(state: dict[str, Any]) -> dict[str, Any] | None:
    node_c = next(node for node in state["nodes"] if node["id"] == "node-c")
    if node_c.get("vibration_score", 0) > 0.75:
        return _finding(
            "vibration_health_agent",
            "ORANGE",
            0.8,
            ["node-c", "coolant-loop-a"],
            "Structure-borne vibration suggests a cooling loop anomaly.",
            ["Vibration score is above 0.75", "Node C has thermal hotspot", "Cooling status is degraded"],
            "Cooling loop fault could worsen thermal risk.",
            ["snapshot_evidence", "run_health_check", "mark_node_suspect"],
            "vibration_cooling_loop",
        )
    return None


AGENT_BUILDERS = [
    build_workload_finding,
    build_thermal_finding,
    build_radiation_finding,
    build_checkpoint_downlink_finding,
    build_vibration_finding,
]

PHASE4_AGENT_NAMES = [
    "workload_agent",
    "thermal_physical_agent",
    "radiation_integrity_agent",
    "checkpoint_downlink_agent",
    "vibration_health_agent",
]


async def run_remaining_agents_once() -> list[AgentFinding]:
    async with session_context() as session:
        result = await session.execute(select(WorldStateCurrent).where(WorldStateCurrent.id.is_(True)))
        world_state = result.scalar_one_or_none()
        if world_state is None:
            return []
        payloads = [payload for builder in AGENT_BUILDERS if (payload := builder(world_state.state)) is not None]

    findings: list[AgentFinding] = []
    for payload in payloads:
        finding = await _persist_finding(payload)
        if finding is not None:
            findings.append(finding)
            await _publish_finding(finding, payload)
    return findings


async def _persist_finding(payload: dict[str, Any]) -> AgentFinding | None:
    async with session_context() as session:
        existing = await find_existing_open_finding(session, payload)
        if existing is not None:
            return None
        await emit_agent_status(
            session,
            agent_name=payload["agent_name"],
            status="detecting",
            phase="detect",
            severity=payload["severity"],
            message=payload["finding"],
        )
        await session.commit()

    async with session_context() as session:
        existing = await find_existing_open_finding(session, payload)
        if existing is not None:
            return None
        finding = AgentFinding(scenario_run_id=DEMO_SCENARIO_RUN_ID, status="open", **payload)
        session.add(finding)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        await session.refresh(finding)

    async with session_context() as session:
        await emit_agent_status(
            session,
            agent_name=payload["agent_name"],
            status="proposing",
            phase="propose",
            severity=payload["severity"],
            message="Finding proposed to Commander.",
            linked_finding_id=finding.id,
        )
        await session.commit()
    return finding


async def find_existing_open_finding(session, payload: dict[str, Any]) -> AgentFinding | None:
    existing_result = await session.execute(
        select(AgentFinding).where(
            AgentFinding.scenario_run_id == DEMO_SCENARIO_RUN_ID,
            AgentFinding.agent_name == payload["agent_name"],
            AgentFinding.finding_signature == payload["finding_signature"],
            AgentFinding.scenario_time_bucket == payload["scenario_time_bucket"],
            AgentFinding.status == "open",
        )
    )
    return existing_result.scalar_one_or_none()


async def _publish_finding(finding: AgentFinding, payload: dict[str, Any]) -> None:
    event = {
        "type": "agent.finding.created",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {"id": finding.id, **payload},
    }
    await publish_stream_event(StreamName.agent_findings.value, event)
    await publish_stream_event(StreamName.ui_events.value, event)


async def emit_phase4_heartbeats_once() -> None:
    for agent_name in PHASE4_AGENT_NAMES:
        async with session_context() as session:
            status_result = await session.execute(select(AgentStatus).where(AgentStatus.agent == agent_name))
            current = status_result.scalar_one_or_none()
            payload = heartbeat_status_payload(current)
            await emit_agent_status(
                session,
                agent_name=agent_name,
                status=payload["status"],
                phase=payload["phase"],
                severity=payload["severity"],
                message=payload["message"],
            )
            await session.commit()


def heartbeat_status_payload(current: AgentStatus | None) -> dict[str, str]:
    if current is None:
        return {
            "status": "monitoring",
            "phase": "monitor",
            "severity": "INFO",
            "message": "Heartbeat: monitoring assigned domain.",
        }
    return {
        "status": current.status,
        "phase": current.phase,
        "severity": current.severity,
        "message": current.message,
    }


def _finding(
    agent_name: str,
    severity: str,
    confidence: float,
    affected_assets: list[str],
    finding: str,
    evidence: list[str],
    risk: str,
    recommended_actions: list[str],
    signature: str,
) -> dict[str, Any]:
    return {
        "agent_name": agent_name,
        "severity": severity,
        "confidence": confidence,
        "affected_assets": affected_assets,
        "finding": finding,
        "evidence": evidence,
        "risk": risk,
        "recommended_actions": recommended_actions,
        "finding_signature": signature,
        "scenario_time_bucket": "phase4-demo",
    }
