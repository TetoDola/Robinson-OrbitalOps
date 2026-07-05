"""Remaining domain agents for Phase 4."""

from __future__ import annotations

import math
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
from app.services.llm_client import active_text_model_label, agent_analysis_is_enabled, analyze_agent_finding


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


# One usable ground-contact window per orbit at demo LEO altitude.
DOWNLINK_ORBIT_PERIOD_MIN = 92.5
# Fraction of a contact window's capacity a chunk may use; the rest is margin
# for link degradation, retransmits, and protocol overhead.
DOWNLINK_SAFE_WINDOW_FRACTION = 0.85


def plan_downlink_chunks(downlink: dict[str, Any]) -> dict[str, Any] | None:
    """Chunk a pending bulk-data request into safe per-window transfers.

    Returns None when there is no pending request or no usable window capacity.
    """
    request = downlink.get("pending_request") or {}
    request_gb = _number(request.get("size_gb"))
    capacity_gb = _number(downlink.get("capacity_gb")) or 0
    if not request_gb or request_gb <= 0 or capacity_gb <= 0:
        return None

    chunk_gb = max(1, math.floor(capacity_gb * DOWNLINK_SAFE_WINDOW_FRACTION))
    chunk_count = math.ceil(request_gb / chunk_gb)
    orbits_needed = chunk_count  # one contact window per orbit
    total_minutes = orbits_needed * DOWNLINK_ORBIT_PERIOD_MIN
    return {
        "request_id": request.get("id"),
        "request_description": request.get("description"),
        "request_gb": request_gb,
        "window_capacity_gb": capacity_gb,
        "chunk_gb": chunk_gb,
        "chunk_count": chunk_count,
        "orbits_needed": orbits_needed,
        "estimated_hours": round(total_minutes / 60, 1),
        "estimated_days": round(total_minutes / 1440, 1),
    }


def build_checkpoint_downlink_finding(state: dict[str, Any]) -> dict[str, Any] | None:
    downlink = state["downlink"]
    plan = plan_downlink_chunks(downlink)
    if plan is not None and plan["request_gb"] > plan["window_capacity_gb"]:
        request_tb = plan["request_gb"] / 1024
        description = plan["request_description"] or "bulk model data"
        return _finding(
            "checkpoint_downlink_agent",
            "YELLOW",
            0.84,
            [asset for asset in (plan["request_id"], "ground-link") if asset],
            f"{request_tb:.1f} TB data request exceeds single-window capacity; chunked transfer plan prepared.",
            [
                f"Ground requested {request_tb:.1f} TB ({plan['request_gb']:.0f} GB) of {description}",
                f"Contact window capacity is {plan['window_capacity_gb']:.0f} GB; safe chunk size with "
                f"{round((1 - DOWNLINK_SAFE_WINDOW_FRACTION) * 100)}% link margin is {plan['chunk_gb']} GB",
                f"Transfer needs {plan['chunk_count']} chunks at one contact window per orbit -> {plan['orbits_needed']} orbits",
                f"Orbit period ~{DOWNLINK_ORBIT_PERIOD_MIN:g} min -> estimated completion in ~{plan['estimated_days']} days "
                f"({plan['estimated_hours']} hours) of chunked downlink",
            ],
            "Sending oversized transfers risks window overrun and corrupted partial chunks; "
            "the request must be chunked and scheduled across contact windows.",
            ["transfer_priority"],
            "downlink_chunked_transfer_plan",
        )
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

AGENT_BUILDER_NAMES = {
    build_workload_finding: "workload_agent",
    build_thermal_finding: "thermal_physical_agent",
    build_radiation_finding: "radiation_integrity_agent",
    build_checkpoint_downlink_finding: "checkpoint_downlink_agent",
    build_vibration_finding: "vibration_health_agent",
}

AGENT_HEALTHY_MESSAGES = {
    "workload_agent": "Analyzed scheduler, GPU utilization, and rank lag; no workload anomaly requires action.",
    "thermal_physical_agent": "Analyzed temperature, hotspot, cooling, and vibration inputs; thermal envelope is nominal.",
    "power_orbit_agent": "Analyzed battery, solar, eclipse, and checkpoint inputs; no power/orbit action is required.",
    "radiation_integrity_agent": "Analyzed ECC, Xid, checkpoint trust, and radiation model; no integrity action is required.",
    "checkpoint_downlink_agent": "Analyzed checkpoint size and downlink capacity; recovery artifacts fit current constraints.",
    "vibration_health_agent": "Analyzed vibration and thermal correlation; no cooling-loop intervention is required.",
    "commander_agent": "Watching domain findings and mission patch state for grouping work.",
}

PHASE4_AGENT_NAMES = [
    "workload_agent",
    "thermal_physical_agent",
    "radiation_integrity_agent",
    "checkpoint_downlink_agent",
    "vibration_health_agent",
]

RUNTIME_HEARTBEAT_AGENT_NAMES = [
    "workload_agent",
    "thermal_physical_agent",
    "power_orbit_agent",
    "radiation_integrity_agent",
    "checkpoint_downlink_agent",
    "vibration_health_agent",
    "commander_agent",
]


async def run_remaining_agents_once(state: dict[str, Any] | None = None) -> list[AgentFinding]:
    agent_state = state if state is not None else await read_current_agent_state()
    if agent_state is None:
        return []

    findings: list[AgentFinding] = []
    for builder in AGENT_BUILDERS:
        agent_name = AGENT_BUILDER_NAMES[builder]
        await _emit_analysis_started(agent_name)
        payload = builder(agent_state)
        if payload is None:
            await _emit_analysis_clear(agent_name)
            continue
        # Skip the model call and insert when this signature was already
        # reported (open) or decided by the operator (rejected/resolved).
        existing = await _existing_finding(payload)
        if existing is not None:
            await _emit_duplicate_suppressed(agent_name, payload, existing)
            continue
        if _agent_analysis_enabled():
            await _emit_model_request(agent_name)
        payload, analysis = await _apply_agent_analysis(agent_state, payload)
        if analysis:
            await _emit_model_reply(agent_name, analysis)
        elif _agent_analysis_enabled():
            await _emit_model_fallback(agent_name)
        finding = await _persist_finding(payload)
        if finding is not None:
            findings.append(finding)
            await _publish_finding(finding, payload)
    return findings


async def _emit_analysis_started(agent_name: str) -> None:
    async with session_context() as session:
        await emit_agent_status(
            session,
            agent_name=agent_name,
            status="analyzing",
            phase="detect",
            severity="INFO",
            message=f"Commander dispatch received; {_simple_trigger_message(agent_name)}",
        )
        await session.commit()


async def _emit_analysis_clear(agent_name: str) -> None:
    async with session_context() as session:
        await emit_agent_status(
            session,
            agent_name=agent_name,
            status="monitoring",
            phase="monitor",
            severity="INFO",
            message=AGENT_HEALTHY_MESSAGES.get(agent_name, "Analyzed runtime data; no action is required."),
        )
        await session.commit()


async def _emit_model_request(agent_name: str) -> None:
    async with session_context() as session:
        await emit_agent_status(
            session,
            agent_name=agent_name,
            status="analyzing",
            phase="model",
            severity="INFO",
            message=f"Sending gathered details to {active_text_model_label()}.",
        )
        await session.commit()


async def _emit_model_reply(agent_name: str, analysis: dict[str, Any]) -> None:
    async with session_context() as session:
        await emit_agent_status(
            session,
            agent_name=agent_name,
            status="analyzing",
            phase="model",
            severity="INFO",
            message=(
                f"{analysis.get('model') or active_text_model_label()} replied in {_latency_seconds(analysis.get('latency_ms'))}; "
                "sending analyzed finding to Commander."
            ),
        )
        await session.commit()


async def _emit_model_fallback(agent_name: str) -> None:
    async with session_context() as session:
        await emit_agent_status(
            session,
            agent_name=agent_name,
            status="analyzing",
            phase="model",
            severity="INFO",
            message="Model advisory did not return; using deterministic agent evidence.",
        )
        await session.commit()


async def _apply_agent_analysis(state: dict[str, Any], payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    analysis = await analyze_agent_finding(
        agent_name=payload["agent_name"],
        state=state,
        finding=payload,
    )
    if not analysis:
        return payload, None

    evidence = list(payload["evidence"])
    if analysis.get("summary"):
        evidence.append(f"{_provider_label(analysis)} advisory summary: {analysis['summary']}")
    evidence.extend(f"{_provider_label(analysis)} evidence: {item}" for item in analysis.get("evidence", []))
    if analysis.get("latency_ms") is not None:
        evidence.append(f"{analysis.get('model') or active_text_model_label()} replied in {_latency_seconds(analysis['latency_ms'])}.")
    recommended_actions = _dedupe_strings([*payload["recommended_actions"], *analysis.get("recommended_actions", [])])
    confidence = analysis.get("confidence")
    return (
        {
            **payload,
            "confidence": max(payload["confidence"], confidence) if isinstance(confidence, float) else payload["confidence"],
            "evidence": _dedupe_strings(evidence),
            "risk": analysis.get("risk") or payload["risk"],
            "recommended_actions": recommended_actions,
        },
        analysis,
    )


async def _persist_finding(payload: dict[str, Any]) -> AgentFinding | None:
    async with session_context() as session:
        existing = await find_existing_open_finding(session, payload)
        if existing is not None:
            await _emit_duplicate_suppressed_in_session(session, payload["agent_name"], payload, existing)
            await session.commit()
            return None
        await emit_agent_status(
            session,
            agent_name=payload["agent_name"],
            status="explaining",
            phase="explain",
            severity=payload["severity"],
            message="Building report from telemetry, evidence, and model analysis.",
        )
        await session.commit()

    async with session_context() as session:
        existing = await find_existing_open_finding(session, payload)
        if existing is not None:
            await _emit_duplicate_suppressed_in_session(session, payload["agent_name"], payload, existing)
            await session.commit()
            return None
        finding = AgentFinding(scenario_run_id=DEMO_SCENARIO_RUN_ID, status="open", **payload)
        session.add(finding)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await find_existing_open_finding(session, payload)
            if existing is not None:
                await _emit_duplicate_suppressed_in_session(session, payload["agent_name"], payload, existing)
                await session.commit()
            return None
        await session.refresh(finding)

    async with session_context() as session:
        await emit_agent_status(
            session,
            agent_name=payload["agent_name"],
            status="proposing",
            phase="propose",
            severity=payload["severity"],
            message="Finding sent to Commander.",
            linked_finding_id=finding.id,
        )
        await session.commit()
    return finding


async def find_existing_open_finding(session, payload: dict[str, Any]) -> AgentFinding | None:
    """Match any prior finding with this signature regardless of status.

    The unique constraint spans all statuses, so a rejected or resolved
    finding also blocks re-creation until the demo reset clears the table.
    """
    existing_result = await session.execute(
        select(AgentFinding).where(
            AgentFinding.scenario_run_id == DEMO_SCENARIO_RUN_ID,
            AgentFinding.agent_name == payload["agent_name"],
            AgentFinding.finding_signature == payload["finding_signature"],
            AgentFinding.scenario_time_bucket == payload["scenario_time_bucket"],
        )
    )
    return existing_result.scalar_one_or_none()


async def _existing_finding(payload: dict[str, Any]) -> AgentFinding | None:
    async with session_context() as session:
        return await find_existing_open_finding(session, payload)


async def _emit_duplicate_suppressed(agent_name: str, payload: dict[str, Any], existing: AgentFinding) -> None:
    async with session_context() as session:
        await _emit_duplicate_suppressed_in_session(session, agent_name, payload, existing)
        await session.commit()


async def _emit_duplicate_suppressed_in_session(
    session,
    agent_name: str,
    payload: dict[str, Any],
    existing: AgentFinding,
) -> None:
    if existing.status == "open":
        status, phase, severity = "proposing", "propose", payload["severity"]
        message = "Finding already reported; awaiting Commander grouping and approval outcome."
    elif existing.status == "rejected":
        status, phase, severity = "monitoring", "monitor", "INFO"
        message = "Operator rejected the related mission patch; suppressing repeat of the same finding."
    else:
        status, phase, severity = "monitoring", "monitor", "INFO"
        message = "Previously reported finding was resolved; monitoring for new changes."
    await emit_agent_status(
        session,
        agent_name=agent_name,
        status=status,
        phase=phase,
        severity=severity,
        message=message,
        linked_finding_id=existing.id,
    )


async def _publish_finding(finding: AgentFinding, payload: dict[str, Any]) -> None:
    event = {
        "type": "agent.finding.created",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {"id": finding.id, **payload},
    }
    await publish_stream_event(StreamName.agent_findings.value, event)
    await publish_stream_event(StreamName.ui_events.value, event)


async def emit_phase4_heartbeats_once() -> None:
    for agent_name in RUNTIME_HEARTBEAT_AGENT_NAMES:
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


def _agent_analysis_enabled() -> bool:
    return agent_analysis_is_enabled()


def _provider_label(analysis: dict[str, Any]) -> str:
    provider = str(analysis.get("provider") or "model").lower()
    return "OpenRouter" if provider == "openrouter" else "Crusoe" if provider == "crusoe" else "Model"


def _simple_trigger_message(agent_name: str) -> str:
    messages = {
        "workload_agent": "workload signal detected; gathering GPU utilization, rank lag, and training state.",
        "thermal_physical_agent": "high temperature detected; gathering thermal, cooling, vibration, and visual data.",
        "radiation_integrity_agent": "radiation/integrity signal detected; gathering ECC, Xid, loss, and checkpoint data.",
        "checkpoint_downlink_agent": "downlink constraint detected; gathering checkpoint and contact-window data.",
        "vibration_health_agent": "vibration signal detected; gathering cooling and hotspot correlation data.",
    }
    return messages.get(agent_name, "runtime change detected; gathering assigned telemetry.")


def _latency_seconds(value: Any) -> str:
    try:
        milliseconds = float(value)
    except (TypeError, ValueError):
        return "unknown time"
    return f"{milliseconds / 1000:.1f}s"


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
