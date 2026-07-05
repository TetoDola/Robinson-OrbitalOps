"""Agent lifecycle status emitter."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEMO_SCENARIO_RUN_ID, StreamName
from app.db.models import AgentStatus, AgentStatusEvent
from app.services.event_bus import publish_stream_event


AGENT_DISPLAY_NAMES = {
    "workload_agent": "Workload Agent",
    "thermal_physical_agent": "Thermal / Physical Agent",
    "power_orbit_agent": "Power / Orbit Agent",
    "radiation_integrity_agent": "Radiation / Integrity Agent",
    "checkpoint_downlink_agent": "Checkpoint / Downlink Agent",
    "vibration_health_agent": "Vibration Health Agent",
    "commander_agent": "Commander Agent",
}


async def emit_agent_status(
    session: AsyncSession,
    *,
    agent_name: str,
    status: str,
    phase: str,
    severity: str,
    message: str,
    linked_finding_id: str | None = None,
    linked_incident_id: str | None = None,
    linked_mission_patch_id: str | None = None,
    publish: bool = True,
) -> dict:
    display_name = AGENT_DISPLAY_NAMES.get(agent_name, agent_name.replace("_", " ").title())
    result = await session.execute(select(AgentStatus).where(AgentStatus.agent == agent_name))
    row = result.scalar_one_or_none()
    if row is not None:
        now = datetime.now(timezone.utc)
        row.display_name = display_name
        row.status = status
        row.phase = phase
        row.severity = severity
        row.message = message
        row.linked_mission_patch_id = linked_mission_patch_id
        row.updated_by = agent_name
        row.updated_at = now

    event = AgentStatusEvent(
        scenario_run_id=DEMO_SCENARIO_RUN_ID,
        agent_name=agent_name,
        display_name=display_name,
        status=status,
        phase=phase,
        severity=severity,
        message=message,
        linked_finding_id=linked_finding_id,
        linked_incident_id=linked_incident_id,
        linked_mission_patch_id=linked_mission_patch_id,
        metadata_={"source": agent_name},
    )
    session.add(event)
    payload = {
        "type": "agent.status.updated",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "agent": agent_name,
            "display_name": display_name,
            "status": status,
            "phase": phase,
            "severity": severity,
            "message": message,
            "linked_finding_id": linked_finding_id,
            "linked_incident_id": linked_incident_id,
            "linked_mission_patch_id": linked_mission_patch_id,
        },
    }
    if publish:
        await publish_stream_event(StreamName.agent_status.value, payload)
        await publish_stream_event(StreamName.ui_events.value, payload)
    return payload
