"""Commander Agent for deterministic Phase 3 mission patch generation."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.constants import DEMO_SCENARIO_RUN_ID, StreamName
from app.db.models import AgentFinding, Incident, MissionPatch
from app.db.session import session_context
from app.services.agent_status import emit_agent_status
from app.services.event_bus import publish_stream_event


PATCH_ACTIONS = [
    {"type": "increase_checkpoint_frequency", "job_id": "llm-train-042", "interval_minutes": 15},
    {"type": "set_gpu_power_limit", "node_id": "node-a", "power_percent": 70},
    {
        "type": "transfer_priority",
        "send_first": ["checkpoint_manifest", "checkpoint_hashes", "training_logs", "delta_checkpoint"],
        "defer": ["full_checkpoint"],
    },
]


async def build_phase3_patch() -> MissionPatch | None:
    created_patch = False
    async with session_context() as session:
        await emit_agent_status(
            session,
            agent_name="commander_agent",
            status="monitoring",
            phase="monitor",
            severity="INFO",
            message="Checking open findings for mission patch grouping.",
        )
        findings_result = await session.execute(
            select(AgentFinding).where(
                AgentFinding.scenario_run_id == DEMO_SCENARIO_RUN_ID,
                AgentFinding.agent_name == "power_orbit_agent",
                AgentFinding.status == "open",
            )
        )
        findings = list(findings_result.scalars().all())
        if not findings:
            await session.commit()
            return None
        await emit_agent_status(
            session,
            agent_name="commander_agent",
            status="proposing",
            phase="propose",
            severity="ORANGE",
            message="Grouping Power / Orbit finding into a mission patch.",
            linked_finding_id=findings[0].id,
        )

        incident_key = "training_continuity_risk:llm-train-042:eclipse"
        incident_result = await session.execute(
            select(Incident).where(
                Incident.scenario_run_id == DEMO_SCENARIO_RUN_ID,
                Incident.incident_key == incident_key,
            )
        )
        incident = incident_result.scalar_one_or_none()
        if incident is None:
            incident = Incident(
                scenario_run_id=DEMO_SCENARIO_RUN_ID,
                incident_key=incident_key,
                title="Training continuity risk before eclipse",
                severity="ORANGE",
                status="pending_approval",
                finding_ids=[finding.id for finding in findings],
                summary="Power/Orbit Agent found eclipse risk with degraded battery and suspect checkpoint.",
            )
            session.add(incident)
            await session.flush()

        patch_result = await session.execute(
            select(MissionPatch).where(
                MissionPatch.scenario_run_id == DEMO_SCENARIO_RUN_ID,
                MissionPatch.incident_id == incident.id,
                MissionPatch.status.in_(["pending_approval", "approved", "executing", "verified"]),
            )
        )
        patch = patch_result.scalar_one_or_none()
        if patch is None:
            patch = MissionPatch(
                scenario_run_id=DEMO_SCENARIO_RUN_ID,
                incident_id=incident.id,
                severity="ORANGE",
                status="pending_approval",
                summary="Prepare training for eclipse by increasing checkpoints, reducing GPU power, and prioritizing downlink metadata.",
                evidence=[
                    {"agent": finding.agent_name, "finding": finding.finding, "evidence": finding.evidence}
                    for finding in findings
                ],
                actions=PATCH_ACTIONS,
                rollback_plan={"if_verification_fails": ["pause_job", "snapshot_evidence"]},
                approval_required=True,
            )
            session.add(patch)
            created_patch = True
            await session.commit()
            await session.refresh(patch)
        else:
            await session.commit()

    if not created_patch:
        return patch

    await publish_stream_event(
        StreamName.commander_patches.value,
        {
            "type": "mission_patch.created",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {"id": patch.id, "status": patch.status, "actions": patch.actions},
        },
    )
    await publish_stream_event(
        StreamName.ui_events.value,
        {
            "type": "mission_patch.created",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {"id": patch.id, "status": patch.status, "summary": patch.summary},
        },
    )
    return patch
