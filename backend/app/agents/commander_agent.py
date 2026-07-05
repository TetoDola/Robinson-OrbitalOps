"""Commander Agent for grouping findings into validated mission patches."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.constants import CANONICAL_WORLD_STATE, DEMO_SCENARIO_RUN_ID, CommandType, StreamName
from app.core.safety import SafetyResult, validate_mission_patch
from app.db.models import AgentFinding, Incident, MissionPatch, WorldStateCurrent
from app.db.session import session_context
from app.services.agent_status import emit_agent_status
from app.services.event_bus import publish_stream_event
from app.services.llm_client import polish_mission_patch_summary


MISSION_INCIDENT_KEY = "training_continuity_risk:llm-train-042:combined"
SEVERITY_ORDER = {"INFO": 0, "YELLOW": 1, "ORANGE": 2, "RED": 3}


def build_mission_patch_actions(world_state: dict[str, Any], findings: list[AgentFinding | dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize agent recommendations into canonical executable commands."""
    recommendations = _finding_recommendations(findings)
    training = world_state["training"]
    actions: list[dict[str, Any]] = []

    if CommandType.mark_checkpoint_suspect.value in recommendations or training.get("latest_checkpoint_status") == "suspect":
        actions.append({"type": CommandType.mark_checkpoint_suspect.value, "checkpoint_id": training["latest_checkpoint"]})
        actions.append(
            {
                "type": CommandType.rollback_training.value,
                "job_id": training["job_id"],
                "checkpoint_id": training["last_trusted_checkpoint"],
            }
        )

    if CommandType.cordon_node.value in recommendations:
        for node_id in _recommended_cordon_nodes(findings):
            actions.append({"type": CommandType.cordon_node.value, "node_id": node_id, "scope": "critical_training"})

    if CommandType.mark_node_suspect.value in recommendations:
        actions.append(
            {
                "type": CommandType.mark_node_suspect.value,
                "node_id": "node-c",
                "reason": "thermal_physical_risk",
            }
        )

    if CommandType.set_gpu_power_limit.value in recommendations:
        actions.append({"type": CommandType.set_gpu_power_limit.value, "node_id": "node-a", "power_percent": 70})

    if CommandType.increase_checkpoint_frequency.value in recommendations:
        actions.append(
            {
                "type": CommandType.increase_checkpoint_frequency.value,
                "job_id": training["job_id"],
                "interval_minutes": 15,
            }
        )

    if CommandType.transfer_priority.value in recommendations:
        actions.append(
            {
                "type": CommandType.transfer_priority.value,
                "send_first": ["checkpoint_manifest", "checkpoint_hashes", "training_logs", "delta_checkpoint"],
                "defer": ["full_checkpoint"],
            }
        )

    if CommandType.snapshot_evidence.value in recommendations:
        actions.append(
            {
                "type": CommandType.snapshot_evidence.value,
                "asset_ids": _affected_assets(findings),
                "include": ["telemetry", "agent_findings", "checkpoint_manifest"],
            }
        )

    if CommandType.run_health_check.value in recommendations:
        actions.append(
            {
                "type": CommandType.run_health_check.value,
                "asset_id": "node-a",
                "check_suite": "distributed_training",
            }
        )

    return _dedupe_actions(actions)


async def build_phase3_patch() -> MissionPatch | None:
    """Compatibility wrapper used by the existing worker entry point."""
    return await build_commander_patch()


async def build_commander_patch() -> MissionPatch | None:
    created_patch = False
    async with session_context() as session:
        world_state_row = await _current_world_state(session)
        world_state = world_state_row.state if world_state_row is not None else CANONICAL_WORLD_STATE
        findings = await _open_findings(session)
        await emit_agent_status(
            session,
            agent_name="commander_agent",
            status="monitoring",
            phase="monitor",
            severity="INFO",
            message="Checking open findings for mission patch grouping.",
        )
        if not findings:
            await session.commit()
            return None

        severity = _max_severity(findings)
        await emit_agent_status(
            session,
            agent_name="commander_agent",
            status="proposing",
            phase="propose",
            severity=severity,
            message="Fusing active agent findings into a mission patch.",
            linked_finding_id=findings[0].id,
        )

        incident = await _get_or_create_incident(session, findings, severity, status="detected")
        existing_patch = await _active_patch_for_incident(session, incident.id)
        if existing_patch is not None:
            await session.commit()
            return existing_patch

        actions = build_mission_patch_actions(world_state, findings)
        safety = validate_mission_patch(actions, world_state)
        if not safety.allowed:
            await _record_blocked_commander_status(session, safety)
            await session.commit()
            return None

        incident.status = "pending_approval"
        incident.updated_at = datetime.now(timezone.utc)
        summary = await polish_mission_patch_summary(_summary(findings), {"world_state": world_state, "findings": findings})
        patch = MissionPatch(
            scenario_run_id=DEMO_SCENARIO_RUN_ID,
            incident_id=incident.id,
            severity=severity,
            status="pending_approval",
            summary=summary,
            evidence=[_evidence_item(finding) for finding in findings],
            actions=actions,
            rollback_plan={"if_verification_fails": ["pause_job", "snapshot_evidence", "resume_from_ground_confirmed_checkpoint"]},
            approval_required=safety.approval_required,
        )
        session.add(patch)
        created_patch = True
        await session.commit()
        await session.refresh(patch)

    if created_patch:
        await _publish_patch_created(patch)
    return patch


async def _current_world_state(session) -> WorldStateCurrent | None:
    result = await session.execute(select(WorldStateCurrent).where(WorldStateCurrent.id.is_(True)))
    return result.scalar_one_or_none()


async def _open_findings(session) -> list[AgentFinding]:
    result = await session.execute(
        select(AgentFinding)
        .where(
            AgentFinding.scenario_run_id == DEMO_SCENARIO_RUN_ID,
            AgentFinding.status == "open",
        )
        .order_by(AgentFinding.created_at.asc())
    )
    return list(result.scalars().all())


async def _get_or_create_incident(session, findings: list[AgentFinding], severity: str, status: str) -> Incident:
    result = await session.execute(
        select(Incident).where(
            Incident.scenario_run_id == DEMO_SCENARIO_RUN_ID,
            Incident.incident_key == MISSION_INCIDENT_KEY,
        )
    )
    incident = result.scalar_one_or_none()
    finding_ids = [finding.id for finding in findings]
    if incident is None:
        incident = Incident(
            scenario_run_id=DEMO_SCENARIO_RUN_ID,
            incident_key=MISSION_INCIDENT_KEY,
            title="Training continuity risk before eclipse",
            severity=severity,
            status=status,
            finding_ids=finding_ids,
            summary="Independent agents detected combined training continuity risk.",
        )
        session.add(incident)
        await session.flush()
        return incident

    incident.severity = severity
    incident.status = status
    incident.finding_ids = finding_ids
    incident.summary = "Independent agents detected combined training continuity risk."
    incident.updated_at = datetime.now(timezone.utc)
    return incident


async def _active_patch_for_incident(session, incident_id: str) -> MissionPatch | None:
    result = await session.execute(
        select(MissionPatch).where(
            MissionPatch.scenario_run_id == DEMO_SCENARIO_RUN_ID,
            MissionPatch.incident_id == incident_id,
            MissionPatch.status.in_(["pending_approval", "approved", "executing", "verified"]),
        )
    )
    return result.scalar_one_or_none()


async def _record_blocked_commander_status(session, safety: SafetyResult) -> None:
    await emit_agent_status(
        session,
        agent_name="commander_agent",
        status="blocked",
        phase="propose",
        severity="RED",
        message=f"Mission patch blocked by safety validator: {safety.reason}",
    )


async def _publish_patch_created(patch: MissionPatch) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "id": patch.id,
        "status": patch.status,
        "severity": patch.severity,
        "summary": patch.summary,
        "actions": patch.actions,
        "approval_required": patch.approval_required,
    }
    await publish_stream_event(
        StreamName.commander_patches.value,
        {"type": "mission_patch.created", "timestamp": now, "payload": payload},
    )
    await publish_stream_event(
        StreamName.ui_events.value,
        {"type": "mission_patch.created", "timestamp": now, "payload": payload},
    )


def _summary(findings: list[AgentFinding]) -> str:
    agents = ", ".join(sorted({finding.agent_name.replace("_", " ") for finding in findings}))
    return (
        "Critical training job is at risk due to combined findings from "
        f"{agents}. Roll back to the last trusted checkpoint, preserve evidence, "
        "reduce power risk, and prioritize recoverable downlink artifacts."
    )


def _evidence_item(finding: AgentFinding) -> dict[str, Any]:
    return {
        "agent": finding.agent_name,
        "finding": finding.finding,
        "severity": finding.severity,
        "confidence": float(finding.confidence),
        "evidence": finding.evidence,
    }


def _finding_recommendations(findings: list[AgentFinding | dict[str, Any]]) -> set[str]:
    recommendations: set[str] = set()
    for finding in findings:
        values = finding["recommended_actions"] if isinstance(finding, dict) else finding.recommended_actions
        recommendations.update(values)
    return recommendations


def _recommended_cordon_nodes(findings: list[AgentFinding | dict[str, Any]]) -> list[str]:
    nodes: list[str] = []
    for finding in findings:
        affected_assets = finding["affected_assets"] if isinstance(finding, dict) else finding.affected_assets
        for asset in affected_assets:
            if asset == "node-b" and asset not in nodes:
                nodes.append(asset)
    return nodes or ["node-b"]


def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for action in actions:
        key = (
            action["type"],
            str(
                action.get("node_id")
                or action.get("checkpoint_id")
                or action.get("job_id")
                or action.get("asset_id")
                or "global"
            ),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return deduped


def _max_severity(findings: list[AgentFinding]) -> str:
    return max((finding.severity for finding in findings), key=lambda value: SEVERITY_ORDER.get(value, 0))


def _affected_assets(findings: list[AgentFinding | dict[str, Any]]) -> list[str]:
    assets: list[str] = []
    for finding in findings:
        affected_assets = finding["affected_assets"] if isinstance(finding, dict) else finding.affected_assets
        for asset in affected_assets:
            if asset not in assets:
                assets.append(asset)
    return assets or ["orbital-dc-01"]


PATCH_ACTIONS = build_mission_patch_actions(CANONICAL_WORLD_STATE, [])
