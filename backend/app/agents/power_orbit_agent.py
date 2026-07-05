"""Power / Orbit Agent for the first vertical slice."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.agents.data_context import build_agent_world_state
from app.agents.domain_agents import find_existing_open_finding
from app.config import settings
from app.constants import DEMO_SCENARIO_RUN_ID, StreamName
from app.db.models import AgentFinding
from app.db.session import session_context
from app.services.agent_status import emit_agent_status
from app.services.event_bus import publish_stream_event
from app.services.llm_client import analyze_agent_finding


def build_power_orbit_finding(state: dict[str, Any]) -> dict[str, Any] | None:
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


async def run_once(state: dict[str, Any] | None = None) -> AgentFinding | None:
    async with session_context() as session:
        await emit_agent_status(
            session,
            agent_name="power_orbit_agent",
            status="analyzing",
            phase="detect",
            severity="INFO",
            message="Commander dispatch received; power/orbit signal detected, gathering eclipse, battery, solar, and checkpoint state.",
        )
        agent_state = state if state is not None else await build_agent_world_state(session)
        if agent_state is None:
            await session.commit()
            return None
        finding_payload = build_power_orbit_finding(agent_state)
        if finding_payload is None:
            await emit_agent_status(
                session,
                agent_name="power_orbit_agent",
                status="monitoring",
                phase="monitor",
                severity="INFO",
                message="Analyzed power, orbit, and checkpoint inputs; no mission patch action is required.",
            )
            await session.commit()
            return None
        existing = await find_existing_open_finding(session, finding_payload)
        if existing is not None:
            # Signature already reported or decided; skip the model call and
            # duplicate insert. Only an open finding should re-trigger the
            # Commander's grouping pass.
            await emit_agent_status(
                session,
                agent_name="power_orbit_agent",
                status="proposing" if existing.status == "open" else "monitoring",
                phase="propose" if existing.status == "open" else "monitor",
                severity=finding_payload["severity"] if existing.status == "open" else "INFO",
                message=(
                    "Finding already reported; awaiting Commander grouping and approval outcome."
                    if existing.status == "open"
                    else f"Prior finding is {existing.status}; suppressing repeat of the same finding."
                ),
                linked_finding_id=existing.id,
            )
            await session.commit()
            return existing if existing.status == "open" else None
        if _agent_analysis_enabled():
            await emit_agent_status(
                session,
                agent_name="power_orbit_agent",
                status="analyzing",
                phase="model",
                severity="INFO",
                message=f"Sending gathered details to {settings.crusoe_model}.",
            )
        await session.commit()

    finding_payload, analysis = await _apply_agent_analysis(agent_state, finding_payload)
    if analysis:
        async with session_context() as session:
            await emit_agent_status(
                session,
                agent_name="power_orbit_agent",
                status="analyzing",
                phase="model",
                severity="INFO",
                message=(
                    f"{settings.crusoe_model} replied in {_latency_seconds(analysis.get('latency_ms'))}; "
                    "sending analyzed finding to Commander."
                ),
            )
            await session.commit()
    elif _agent_analysis_enabled():
        async with session_context() as session:
            await emit_agent_status(
                session,
                agent_name="power_orbit_agent",
                status="analyzing",
                phase="model",
                severity="INFO",
                message="Model advisory did not return; using deterministic power/orbit evidence.",
            )
            await session.commit()

    async with session_context() as session:
        await emit_agent_status(
            session,
            agent_name="power_orbit_agent",
            status="explaining",
            phase="explain",
            severity="ORANGE",
            message="Building report from telemetry, evidence, and model analysis.",
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
            message="Finding sent to Commander.",
            linked_finding_id=finding.id,
        )
        await session.commit()
    event = {
        "type": "agent.finding.created",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {"id": finding.id, **finding_payload},
    }
    await publish_stream_event(StreamName.agent_findings.value, event)
    await publish_stream_event(StreamName.ui_events.value, event)
    return finding


async def _apply_agent_analysis(state: dict[str, Any], payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    analysis = await analyze_agent_finding(
        agent_name="power_orbit_agent",
        state=state,
        finding=payload,
    )
    if not analysis:
        return payload, None

    evidence = list(payload["evidence"])
    if analysis.get("summary"):
        evidence.append(f"Crusoe advisory summary: {analysis['summary']}")
    evidence.extend(f"Crusoe evidence: {item}" for item in analysis.get("evidence", []))
    if analysis.get("latency_ms") is not None:
        evidence.append(f"{settings.crusoe_model} replied in {_latency_seconds(analysis['latency_ms'])}.")
    confidence = analysis.get("confidence")
    return (
        {
            **payload,
            "confidence": max(payload["confidence"], confidence) if isinstance(confidence, float) else payload["confidence"],
            "evidence": _dedupe_strings(evidence),
            "risk": analysis.get("risk") or payload["risk"],
            "recommended_actions": _dedupe_strings(
                [*payload["recommended_actions"], *analysis.get("recommended_actions", [])]
            ),
        },
        analysis,
    )


def _agent_analysis_enabled() -> bool:
    return bool(settings.crusoe_enabled and settings.crusoe_api_key and settings.crusoe_agent_analysis_enabled)


def _latency_seconds(value: Any) -> str:
    try:
        milliseconds = float(value)
    except (TypeError, ValueError):
        return "unknown time"
    return f"{milliseconds / 1000:.1f}s"


def _dedupe_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip() or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_once())
