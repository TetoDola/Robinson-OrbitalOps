"""Power / Orbit Agent for the first vertical slice."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.constants import DEMO_SCENARIO_RUN_ID, StreamName
from app.db.models import AgentFinding, WorldStateCurrent
from app.db.session import session_context
from app.services.agent_status import emit_agent_status
from app.services.event_bus import publish_stream_event


def build_power_orbit_finding(state: dict) -> dict | None:
    battery = state["power"]["battery_percent"]
    time_to_eclipse = state["satellite"]["time_to_eclipse_min"]
    latest_status = state["training"]["latest_checkpoint_status"]
    if time_to_eclipse < 15 and battery < 45 and latest_status == "suspect":
        return {
            "agent_name": "power_orbit_agent",
            "severity": "ORANGE",
            "confidence": 0.88,
            "affected_assets": ["orbital-dc-01", "llm-train-042"],
            "finding": "Eclipse begins soon while battery is degraded and the latest checkpoint is suspect.",
            "evidence": [
                f"Time to eclipse is {time_to_eclipse} minutes",
                f"Battery is {battery}%",
                "Latest checkpoint ckpt-184900 is suspect",
            ],
            "risk": "Critical training may lose recoverable progress during eclipse.",
            "recommended_actions": ["increase_checkpoint_frequency", "set_gpu_power_limit", "transfer_priority"],
            "finding_signature": "power_eclipse_checkpoint_risk",
            "scenario_time_bucket": "phase3-demo",
        }
    return None


async def run_once() -> AgentFinding | None:
    async with session_context() as session:
        await emit_agent_status(
            session,
            agent_name="power_orbit_agent",
            status="monitoring",
            phase="monitor",
            severity="INFO",
            message="Reading latest orbital power state.",
        )
        result = await session.execute(select(WorldStateCurrent).where(WorldStateCurrent.id.is_(True)))
        world_state = result.scalar_one_or_none()
        if world_state is None:
            await session.commit()
            return None
        await emit_agent_status(
            session,
            agent_name="power_orbit_agent",
            status="detecting",
            phase="detect",
            severity="INFO",
            message="Checking eclipse, battery, and checkpoint freshness.",
        )
        finding_payload = build_power_orbit_finding(world_state.state)
        if finding_payload is None:
            await emit_agent_status(
                session,
                agent_name="power_orbit_agent",
                status="monitoring",
                phase="monitor",
                severity="INFO",
                message="Power and orbit state are within demo limits.",
            )
            await session.commit()
            return None
        await emit_agent_status(
            session,
            agent_name="power_orbit_agent",
            status="explaining",
            phase="explain",
            severity="ORANGE",
            message="Explaining eclipse/battery/checkpoint risk.",
        )
        finding = AgentFinding(scenario_run_id=DEMO_SCENARIO_RUN_ID, status="open", **finding_payload)
        session.add(finding)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await session.execute(
                select(AgentFinding).where(
                    AgentFinding.scenario_run_id == DEMO_SCENARIO_RUN_ID,
                    AgentFinding.agent_name == "power_orbit_agent",
                    AgentFinding.finding_signature == finding_payload["finding_signature"],
                    AgentFinding.scenario_time_bucket == finding_payload["scenario_time_bucket"],
                )
            )
            return existing.scalar_one_or_none()
        await session.refresh(finding)

    async with session_context() as session:
        await emit_agent_status(
            session,
            agent_name="power_orbit_agent",
            status="proposing",
            phase="propose",
            severity="ORANGE",
            message="Eclipse/battery/checkpoint risk proposed to Commander.",
            linked_finding_id=finding.id,
        )
        await session.commit()
    await publish_stream_event(
        StreamName.agent_findings.value,
        {
            "type": "agent.finding.created",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {"id": finding.id, **finding_payload},
        },
    )
    return finding


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_once())
