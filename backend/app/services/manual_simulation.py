"""Operator-triggered demo injections for the command-center UI."""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from app.agents.commander_agent import build_commander_patch
from app.agents.domain_agents import (
    _persist_finding,
    _publish_finding,
    build_checkpoint_downlink_finding,
    build_radiation_finding,
    build_vibration_finding,
    build_workload_finding,
)
from app.agents.power_orbit_agent import build_power_orbit_finding
from app.config import settings
from app.constants import DEMO_BASELINE_WORLD_STATE, DEMO_SCENARIO_NAME, DEMO_SCENARIO_RUN_ID, StreamName
from app.db.models import ScenarioRun, TelemetryEvent
from app.db.session import session_context
from app.services.agent_status import emit_agent_status
from app.services.event_bus import publish_stream_event
from app.services.llm_client import analyze_thermal_ir_image
from app.services.world_state import read_world_state, write_world_state
from app.schemas.simulator import SimulatorInjectRequest, SimulatorInjectResponse


FindingBuilder = Callable[[dict[str, Any]], dict[str, Any] | None]

SAMPLE_THERMAL_IMAGE_DATA_URL = (
    "data:image/svg+xml;utf8,"
    "%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='320'%20height='180'%20viewBox='0%200%20320%20180'%3E"
    "%3Crect%20width='320'%20height='180'%20fill='%23050a12'/%3E"
    "%3Crect%20x='32'%20y='24'%20width='256'%20height='132'%20rx='8'%20fill='%2313212d'/%3E"
    "%3Cg%20opacity='0.9'%3E"
    "%3Ccircle%20cx='206'%20cy='88'%20r='52'%20fill='%23ff2d1b'/%3E"
    "%3Ccircle%20cx='206'%20cy='88'%20r='32'%20fill='%23ffd166'/%3E"
    "%3Ccircle%20cx='120'%20cy='96'%20r='34'%20fill='%232bb8ff'/%3E"
    "%3C/g%3E"
    "%3Cpath%20d='M48%20144H272'%20stroke='%2389a3b6'%20stroke-width='3'%20stroke-dasharray='8%2010'/%3E"
    "%3Ctext%20x='32'%20y='20'%20fill='%23d9f2ff'%20font-size='12'%20font-family='monospace'%3EIR%20FRAME%20NODE-C%3C/text%3E"
    "%3C/svg%3E"
)


ISSUE_AGENTS: dict[str, tuple[str, str, list[FindingBuilder]]] = {
    "workload-stall": (
        "workload_agent",
        "Rank lag injected on Node A for scheduler/GPU mismatch detection.",
        [build_workload_finding],
    ),
    "eclipse-risk": (
        "power_orbit_agent",
        "Eclipse and battery risk injected for orbit-aware power planning.",
        [build_power_orbit_finding],
    ),
    "radiation-spike": (
        "radiation_integrity_agent",
        "ECC/Xid spike injected for checkpoint integrity detection.",
        [build_radiation_finding],
    ),
    "downlink-constraint": (
        "checkpoint_downlink_agent",
        "Downlink capacity limit injected for recovery artifact prioritization.",
        [build_checkpoint_downlink_finding],
    ),
    "vibration-fault": (
        "vibration_health_agent",
        "Structure-borne vibration anomaly injected for cooling-loop correlation.",
        [build_vibration_finding],
    ),
}


async def inject_named_issue(issue: str, request: SimulatorInjectRequest) -> SimulatorInjectResponse:
    if issue == "thermal-frame":
        return await inject_thermal_frame(request)
    if issue not in ISSUE_AGENTS:
        raise ValueError(f"Unknown simulator issue: {issue}")

    agent_name, status_message, builders = ISSUE_AGENTS[issue]
    timestamp = datetime.now(timezone.utc)
    async with session_context() as session:
        current = await read_world_state(session)
        base_state = deepcopy(current.state if current is not None else DEMO_BASELINE_WORLD_STATE)
        patch = _issue_state_patch(issue, base_state, request)
        world_state = await write_world_state(
            session,
            patch,
            updated_by="operator-simulator",
            reason=f"manual_injection:{issue}",
        )
        await _pause_scenario(session, issue, timestamp)
        await emit_agent_status(
            session,
            agent_name=agent_name,
            status="detecting",
            phase="detect",
            severity="ORANGE",
            message=status_message,
        )
        session.add(
            TelemetryEvent(
                scenario_run_id=DEMO_SCENARIO_RUN_ID,
                event_type=f"simulator.inject.{issue}",
                asset_id=request.asset_id,
                severity="ORANGE",
                payload={"issue": issue, "source": request.source, "notes": request.notes},
                created_at=timestamp,
            )
        )
        await session.commit()

    await _publish_world_state(world_state, timestamp)
    await _publish_injection_event(issue, world_state.version, timestamp, {"source": request.source})

    finding_ids = await _run_builders(world_state.state, builders)
    patch = await build_commander_patch()
    return SimulatorInjectResponse(
        issue=issue,
        status="injected",
        world_state_version=world_state.version,
        finding_ids=finding_ids,
        mission_patch_id=patch.id if patch else None,
    )


async def inject_thermal_frame(request: SimulatorInjectRequest) -> SimulatorInjectResponse:
    timestamp = datetime.now(timezone.utc)
    image_id = str(uuid.uuid4())
    image_data_url = request.image_data_url or SAMPLE_THERMAL_IMAGE_DATA_URL
    latest_input = {
        "id": image_id,
        "asset_id": request.asset_id or "node-c",
        "source": request.source,
        "notes": request.notes,
        "received_at": timestamp.isoformat(),
        "image_data_url": image_data_url,
        "analysis_status": "pending",
        "model_result": None,
    }

    async with session_context() as session:
        current = await read_world_state(session)
        base_state = deepcopy(current.state if current is not None else DEMO_BASELINE_WORLD_STATE)
        world_state = await write_world_state(
            session,
            _thermal_state_patch(base_state, latest_input),
            updated_by="thermal-operator-input",
            reason="thermal_image_input",
        )
        await _pause_scenario(session, "thermal-frame", timestamp)
        await emit_agent_status(
            session,
            agent_name="thermal_physical_agent",
            status="analyzing",
            phase="detect",
            severity="ORANGE",
            message="Thermal frame received; checking visual hotspot evidence.",
        )
        session.add(
            TelemetryEvent(
                scenario_run_id=DEMO_SCENARIO_RUN_ID,
                event_type="thermal.image.received",
                asset_id=latest_input["asset_id"],
                severity="ORANGE",
                payload={key: value for key, value in latest_input.items() if key != "image_data_url"},
                created_at=timestamp,
            )
        )
        await session.commit()

    await _publish_world_state(world_state, timestamp)
    await _publish_injection_event(
        "thermal-frame",
        world_state.version,
        timestamp,
        {"image_id": image_id, "analysis_status": "pending", "asset_id": latest_input["asset_id"]},
    )

    deterministic_finding = _thermal_image_finding(world_state.state, latest_input, None)
    model_result = await analyze_thermal_ir_image(
        image_data_url,
        state=world_state.state,
        finding=deterministic_finding,
    )
    analysis_status = _analysis_status(model_result)
    latest_input["analysis_status"] = analysis_status
    latest_input["model_result"] = model_result

    update_timestamp = datetime.now(timezone.utc)
    async with session_context() as session:
        world_state = await write_world_state(
            session,
            {"thermal": {"latest_visual_input": latest_input}},
            updated_by="thermal-agent",
            reason="thermal_image_analysis",
        )
        await emit_agent_status(
            session,
            agent_name="thermal_physical_agent",
            status="proposing",
            phase="propose",
            severity="RED",
            message=_thermal_status_message(analysis_status, model_result),
        )
        await session.commit()

    await _publish_world_state(world_state, update_timestamp)
    await publish_stream_event(
        StreamName.ui_events.value,
        {
            "type": "thermal.image.analysis_completed",
            "timestamp": update_timestamp.isoformat(),
            "payload": {
                "image_id": image_id,
                "asset_id": latest_input["asset_id"],
                "analysis_status": analysis_status,
                "model_result": model_result,
            },
        },
    )

    payload = _thermal_image_finding(world_state.state, latest_input, model_result)
    finding = await _persist_finding(payload)
    finding_id = finding.id if finding is not None else None
    if finding is not None:
        await _publish_finding(finding, payload)
    patch = await build_commander_patch()

    return SimulatorInjectResponse(
        issue="thermal-frame",
        status="injected",
        world_state_version=world_state.version,
        finding_ids=[finding_id] if finding_id else [],
        image_id=image_id,
        mission_patch_id=patch.id if patch else None,
        analysis_status=analysis_status,
        model_result=model_result,
    )


async def _run_builders(state: dict[str, Any], builders: list[FindingBuilder]) -> list[str]:
    finding_ids: list[str] = []
    for builder in builders:
        payload = builder(state)
        if payload is None:
            continue
        finding = await _persist_finding(payload)
        if finding is None:
            continue
        await _publish_finding(finding, payload)
        finding_ids.append(finding.id)
    return finding_ids


async def _pause_scenario(session, issue: str, timestamp: datetime) -> None:
    scenario = await session.get(ScenarioRun, DEMO_SCENARIO_RUN_ID)
    if scenario is None:
        scenario = ScenarioRun(
            id=DEMO_SCENARIO_RUN_ID,
            scenario_name=DEMO_SCENARIO_NAME,
            status="paused",
            metadata_={},
        )
        session.add(scenario)
    metadata = dict(scenario.metadata_ or {})
    metadata["manual_injection"] = issue
    metadata["manual_injected_at"] = timestamp.isoformat()
    scenario.status = "paused"
    scenario.metadata_ = metadata


async def _publish_world_state(world_state, timestamp: datetime) -> None:
    await publish_stream_event(
        StreamName.ui_events.value,
        {
            "type": "world_state.updated",
            "timestamp": timestamp.isoformat(),
            "payload": {
                "version": world_state.version,
                "scenario_run_id": world_state.scenario_run_id,
                "state": world_state.state,
            },
        },
    )


async def _publish_injection_event(
    issue: str,
    world_state_version: int,
    timestamp: datetime,
    payload: dict[str, Any],
) -> None:
    await publish_stream_event(
        StreamName.ui_events.value,
        {
            "type": "simulator.injected",
            "timestamp": timestamp.isoformat(),
            "payload": {"issue": issue, "world_state_version": world_state_version, **payload},
        },
    )


def _issue_state_patch(issue: str, state: dict[str, Any], request: SimulatorInjectRequest) -> dict[str, Any]:
    if issue == "workload-stall":
        return {
            "nodes": _nodes_with(state, {"node-a": {"gpu_util": 96, "rank_lag": 0.11, "status": "training_straggler"}}),
            "training": {"status": "running", "current_step": 184760, "loss_state": "finite"},
        }
    if issue == "eclipse-risk":
        return {
            "satellite": {"orbit_phase": "approaching_eclipse", "time_to_eclipse_min": 11},
            "power": {"battery_percent": 38, "solar_kw": 1.2, "mode": "degraded_safe"},
            "training": {"latest_checkpoint": "ckpt-184900", "latest_checkpoint_status": "suspect"},
            "downlink": {"capacity_gb": 22, "time_remaining_min": 18},
        }
    if issue == "radiation-spike":
        return {
            "radiation": {"risk": "elevated", "region": "risk-zone-alpha", "ecc_errors_last_5min": 936, "xid_event": True},
            "training": {"latest_checkpoint": "ckpt-184900", "latest_checkpoint_status": "suspect", "loss_state": "nan_detected"},
            "nodes": _nodes_with(
                state,
                {"node-b": {"status": "integrity_risk", "gpu_util": 12, "ecc_errors": 936, "xid_event": True}},
            ),
        }
    if issue == "downlink-constraint":
        return {
            "downlink": {"window_open": True, "capacity_gb": 22, "used_gb": 0, "time_remaining_min": 18},
            "training": {"latest_checkpoint": "ckpt-184900", "latest_checkpoint_status": "trusted"},
        }
    if issue == "vibration-fault":
        return {
            "thermal": {"highest_temp_c": 84, "hotspot_node": request.asset_id, "cooling_status": "degraded"},
            "nodes": _nodes_with(
                state,
                {request.asset_id: {"status": "cooling_loop_risk", "temp_c": 84, "vibration_score": 0.91}},
            ),
        }
    raise ValueError(f"Unsupported simulator issue: {issue}")


def _thermal_state_patch(state: dict[str, Any], latest_input: dict[str, Any]) -> dict[str, Any]:
    asset_id = str(latest_input["asset_id"])
    return {
        "thermal": {
            "highest_temp_c": 91,
            "hotspot_node": asset_id,
            "cooling_status": "degraded",
            "latest_visual_input": latest_input,
        },
        "nodes": _nodes_with(
            state,
            {asset_id: {"status": "thermal_physical_risk", "temp_c": 91, "vibration_score": 0.82}},
        ),
    }


def _nodes_with(state: dict[str, Any], updates: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    nodes = deepcopy(state.get("nodes") or DEMO_BASELINE_WORLD_STATE["nodes"])
    known_ids = {node.get("id") for node in nodes}
    for node in nodes:
        node_id = node.get("id")
        if node_id in updates:
            node.update(updates[node_id])
    for node_id, patch in updates.items():
        if node_id not in known_ids:
            nodes.append({"id": node_id, **patch})
    return nodes


def _thermal_image_finding(
    state: dict[str, Any],
    latest_input: dict[str, Any],
    model_result: dict[str, Any] | None,
) -> dict[str, Any]:
    asset_id = str(latest_input["asset_id"])
    model_evidence = (model_result or {}).get("evidence") or []
    recommended_actions = (model_result or {}).get("recommended_actions") or []
    return {
        "agent_name": "thermal_physical_agent",
        "severity": "RED",
        "confidence": float((model_result or {}).get("confidence") or 0.91),
        "affected_assets": _dedupe([asset_id, *((model_result or {}).get("affected_assets") or [])]),
        "finding": (model_result or {}).get("summary") or f"Thermal frame shows a hotspot on {asset_id}.",
        "evidence": _dedupe(
            [
                f"{asset_id} is the current hotspot asset",
                "Cooling status is degraded",
                "Operator supplied a thermal IR frame",
                *model_evidence,
            ]
        ),
        "risk": (model_result or {}).get("risk") or "Thermal anomaly may make the asset unsafe for critical workloads.",
        "recommended_actions": _dedupe(
            [*recommended_actions, "mark_node_suspect", "set_gpu_power_limit", "run_health_check", "snapshot_evidence"]
        ),
        "finding_signature": "thermal_operator_image_hotspot",
        "scenario_time_bucket": latest_input["id"][:12],
    }


def _analysis_status(model_result: dict[str, Any] | None) -> str:
    if model_result:
        return "completed"
    if not settings.crusoe_enabled or not settings.crusoe_api_key:
        return "blocked_missing_crusoe_config"
    return "failed"


def _thermal_status_message(analysis_status: str, model_result: dict[str, Any] | None) -> str:
    if model_result and model_result.get("summary"):
        return str(model_result["summary"])
    if analysis_status == "blocked_missing_crusoe_config":
        return "Thermal frame stored; Nemotron analysis is waiting for Crusoe credentials."
    return "Thermal frame stored; deterministic telemetry still indicates hotspot risk."


def _dedupe(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip() or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
