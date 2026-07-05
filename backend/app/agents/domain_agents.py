"""Remaining domain agents for Phase 4."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.constants import DEMO_SCENARIO_RUN_ID, StreamName
from app.db.models import AgentFinding, AgentStatus
from app.db.session import session_context
from app.agents.data_context import read_current_agent_state
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
    radiation = state.get("radiation") or {}
    training = state.get("training") or {}
    computed = radiation.get("computed_risk") or {}
    ecc_errors = _number(radiation.get("ecc_errors_last_5min")) or 0
    xid_event = bool(radiation.get("xid_event"))
    latest_checkpoint = str(training.get("latest_checkpoint") or "latest checkpoint")
    checkpoint_status = str(training.get("latest_checkpoint_status") or "unknown")
    loss_state = str(training.get("loss_state") or "")
    computed_score = _number(computed.get("radiationRiskScore"))
    computed_level = str(computed.get("radiationLevel") or "").upper()
    model_high = computed_level in {"HIGH", "CRITICAL"} or (computed_score is not None and computed_score >= 62)
    integrity_signal = ecc_errors > 900 or xid_event or checkpoint_status == "suspect" or "nan" in loss_state.lower()

    if not (ecc_errors > 900 or (model_high and integrity_signal)):
        return None

    affected_assets = _radiation_affected_assets(state, latest_checkpoint)
    evidence = _radiation_evidence(radiation, training, computed)
    confidence = max(0.82, min(0.95, 0.74 + ((computed_score or ecc_errors / 12) / 500)))
    return _finding(
        "radiation_integrity_agent",
        "RED" if ecc_errors > 900 or xid_event or computed_level == "CRITICAL" else "ORANGE",
        round(confidence, 2),
        affected_assets,
        "Radiation and integrity data indicate checkpoint corruption risk.",
        evidence,
        f"{latest_checkpoint} may contain corrupted training state.",
        ["mark_checkpoint_suspect", "cordon_node", "run_health_check"],
        "radiation_checkpoint_integrity",
    )


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


async def run_remaining_agents_once(state: dict[str, Any] | None = None) -> list[AgentFinding]:
    agent_state = state if state is not None else await read_current_agent_state()
    if agent_state is None:
        return []
    payloads = [payload for builder in AGENT_BUILDERS if (payload := builder(agent_state)) is not None]

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


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _radiation_affected_assets(state: dict[str, Any], latest_checkpoint: str) -> list[str]:
    assets: list[str] = []
    for node in state.get("nodes") or []:
        if node.get("xid_event") or (_number(node.get("ecc_errors")) or 0) > 0:
            node_id = node.get("id")
            if isinstance(node_id, str):
                assets.append(node_id)
    assets.append(latest_checkpoint)
    return _dedupe_strings(assets)


def _radiation_evidence(
    radiation: dict[str, Any],
    training: dict[str, Any],
    computed: dict[str, Any],
) -> list[str]:
    evidence: list[str] = []
    if computed.get("available"):
        score = computed.get("radiationRiskScore")
        level = computed.get("radiationLevel")
        if score is not None and level:
            evidence.append(f"Computed radiation risk is {level} ({score}/100).")
        if computed.get("mainCause"):
            evidence.append(f"Dominant radiation driver is {computed['mainCause']}.")
        if computed.get("sourceMode"):
            evidence.append(f"Radiation model source mode is {computed['sourceMode']}.")

    ecc_errors = _number(radiation.get("ecc_errors_last_5min")) or 0
    evidence.append(f"ECC count is {round(ecc_errors)} in the last 5 minutes.")
    if radiation.get("xid_event"):
        evidence.append("Xid event observed.")
    if training.get("latest_checkpoint_status"):
        evidence.append(f"Latest checkpoint is {training['latest_checkpoint_status']}.")
    if training.get("loss_state"):
        evidence.append(f"Training loss state is {training['loss_state']}.")
    return _dedupe_strings(evidence)


def _dedupe_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip() or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
