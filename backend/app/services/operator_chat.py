"""Mission-aware operator chatbot service."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.schemas.chat import ChatTurn
from app.services.llm_client import active_text_model_label, answer_operator_chat


SEVERITY_RANK = {
    "CRITICAL": 0,
    "RED": 1,
    "ORANGE": 2,
    "WARN": 3,
    "WARNING": 3,
    "YELLOW": 4,
    "INFO": 5,
}
MAX_REPLY_CHARS = 1400


@dataclass(frozen=True)
class OperatorChatReply:
    content: str
    source: str
    model: str | None
    context_summary: dict[str, Any]


async def build_operator_chat_reply(
    *,
    message: str,
    history: list[ChatTurn],
    world_state: Any | None,
    agents: list[Any],
    findings: list[Any],
    mission_patch: Any | None,
    commands: list[Any] | None = None,
    scenario_runs: list[Any] | None = None,
    agent_events: list[Any] | None = None,
    incidents: list[Any] | None = None,
    mission_patches: list[Any] | None = None,
    approvals: list[Any] | None = None,
    telemetry_events: list[Any] | None = None,
    world_snapshots: list[Any] | None = None,
) -> OperatorChatReply:
    context = _context_payload(
        world_state=world_state,
        scenario_runs=scenario_runs or [],
        agents=agents,
        agent_events=agent_events or [],
        findings=findings,
        incidents=incidents or [],
        mission_patches=mission_patches or [],
        approvals=approvals or [],
        commands=commands or [],
        telemetry_events=telemetry_events or [],
        world_snapshots=world_snapshots or [],
        mission_patch=mission_patch,
    )
    model_reply = await answer_operator_chat(message=message, history=history, context=context)
    if model_reply:
        return OperatorChatReply(
            content=_bounded(model_reply, MAX_REPLY_CHARS),
            source=_model_source(),
            model=active_text_model_label(),
            context_summary=_context_summary(context),
        )

    direct_reply = _direct_operator_answer(message, context)
    if direct_reply:
        return OperatorChatReply(
            content=_bounded(direct_reply, MAX_REPLY_CHARS),
            source="deterministic",
            model=None,
            context_summary=_context_summary(context),
        )

    return OperatorChatReply(
        content=_fallback_operator_answer(message, context),
        source="deterministic",
        model=None,
        context_summary=_context_summary(context),
    )


def _context_payload(
    *,
    world_state: Any | None,
    scenario_runs: list[Any],
    agents: list[Any],
    agent_events: list[Any],
    findings: list[Any],
    incidents: list[Any],
    mission_patches: list[Any],
    approvals: list[Any],
    commands: list[Any],
    telemetry_events: list[Any],
    world_snapshots: list[Any],
    mission_patch: Any | None,
) -> dict[str, Any]:
    state = getattr(world_state, "state", None) or {}
    sorted_scenario_runs = sorted(scenario_runs, key=lambda item: str(getattr(item, "started_at", "")), reverse=True)
    sorted_agents = sorted(agents, key=lambda item: _severity_rank(getattr(item, "severity", "")))
    sorted_agent_events = sorted(agent_events, key=lambda item: str(getattr(item, "created_at", "")), reverse=True)
    sorted_findings = sorted(
        findings,
        key=lambda item: (
            _severity_rank(getattr(item, "severity", "")),
            str(getattr(item, "created_at", "")),
        ),
    )
    sorted_incidents = sorted(incidents, key=lambda item: str(getattr(item, "updated_at", "")), reverse=True)
    sorted_patches = sorted(mission_patches, key=lambda item: str(getattr(item, "created_at", "")), reverse=True)
    sorted_approvals = sorted(approvals, key=lambda item: str(getattr(item, "created_at", "")), reverse=True)
    sorted_commands = sorted(commands, key=lambda item: str(getattr(item, "created_at", "")), reverse=True)
    sorted_telemetry_events = sorted(telemetry_events, key=lambda item: str(getattr(item, "created_at", "")), reverse=True)
    sorted_snapshots = sorted(world_snapshots, key=lambda item: str(getattr(item, "created_at", "")), reverse=True)

    context = {
        "world": {
            "version": getattr(world_state, "version", None),
            "scenario_run_id": getattr(world_state, "scenario_run_id", None),
            "updated_by": getattr(world_state, "updated_by", None),
            "updated_at": getattr(world_state, "updated_at", None),
            "scenario": state.get("scenario"),
            "scenario_name": state.get("scenario_name"),
            "satellite": state.get("satellite", {}),
            "power": state.get("power", {}),
            "thermal": state.get("thermal", {}),
            "radiation": state.get("radiation", {}),
            "downlink": state.get("downlink", {}),
            "training": state.get("training", {}),
            "nodes": state.get("nodes", []),
            "state": _safe_json(state),
        },
        "scenario_runs": [_scenario_run_payload(row) for row in sorted_scenario_runs[:5]],
        "agents": [_agent_payload(agent) for agent in sorted_agents],
        "agent_events": [_agent_event_payload(event) for event in sorted_agent_events[:25]],
        "findings": [_finding_payload(finding) for finding in sorted_findings[:25]],
        "incidents": [_incident_payload(incident) for incident in sorted_incidents[:25]],
        "mission_patches": [_mission_patch_payload(patch) for patch in sorted_patches[:25]],
        "approvals": [_approval_payload(approval) for approval in sorted_approvals[:25]],
        "commands": [_command_payload(command) for command in sorted_commands[:25]],
        "telemetry_events": [_telemetry_event_payload(event) for event in sorted_telemetry_events[:25]],
        "world_snapshots": [_world_snapshot_payload(snapshot) for snapshot in sorted_snapshots[:5]],
        "mission_patch": _mission_patch_payload(mission_patch),
    }
    context["all_accessible_data"] = {
        "world": context["world"],
        "scenario_runs": context["scenario_runs"],
        "agents": context["agents"],
        "agent_events": context["agent_events"],
        "findings": context["findings"],
        "incidents": context["incidents"],
        "mission_patches": context["mission_patches"],
        "approvals": context["approvals"],
        "commands": context["commands"],
        "telemetry_events": context["telemetry_events"],
        "world_snapshots": context["world_snapshots"],
    }
    return context


def _model_source() -> str:
    if settings.crusoe_enabled and settings.crusoe_api_key:
        return "crusoe"
    return "openrouter"


def _scenario_run_payload(row: Any) -> dict[str, Any]:
    return {
        "id": getattr(row, "id", ""),
        "scenario_name": getattr(row, "scenario_name", ""),
        "status": getattr(row, "status", ""),
        "metadata": _safe_json(getattr(row, "metadata_", {}) or {}),
        "started_at": getattr(row, "started_at", None),
        "ended_at": getattr(row, "ended_at", None),
    }


def _agent_payload(agent: Any) -> dict[str, Any]:
    return {
        "agent": getattr(agent, "agent", ""),
        "display_name": getattr(agent, "display_name", ""),
        "status": getattr(agent, "status", ""),
        "phase": getattr(agent, "phase", ""),
        "severity": getattr(agent, "severity", ""),
        "message": getattr(agent, "message", ""),
        "linked_mission_patch_id": getattr(agent, "linked_mission_patch_id", None),
    }


def _agent_event_payload(event: Any) -> dict[str, Any]:
    return {
        "id": getattr(event, "id", ""),
        "scenario_run_id": getattr(event, "scenario_run_id", None),
        "agent_name": getattr(event, "agent_name", ""),
        "display_name": getattr(event, "display_name", ""),
        "status": getattr(event, "status", ""),
        "phase": getattr(event, "phase", ""),
        "severity": getattr(event, "severity", ""),
        "message": getattr(event, "message", ""),
        "current_task": getattr(event, "current_task", None),
        "progress": _numeric_or_none(getattr(event, "progress", None)),
        "affected_assets": list(getattr(event, "affected_assets", []) or []),
        "linked_finding_id": getattr(event, "linked_finding_id", None),
        "linked_incident_id": getattr(event, "linked_incident_id", None),
        "linked_mission_patch_id": getattr(event, "linked_mission_patch_id", None),
        "metadata": _safe_json(getattr(event, "metadata_", {}) or {}),
        "created_at": getattr(event, "created_at", None),
    }


def _finding_payload(finding: Any) -> dict[str, Any]:
    return {
        "id": getattr(finding, "id", ""),
        "agent_name": getattr(finding, "agent_name", ""),
        "severity": getattr(finding, "severity", ""),
        "confidence": float(getattr(finding, "confidence", 0) or 0),
        "affected_assets": list(getattr(finding, "affected_assets", []) or []),
        "finding": getattr(finding, "finding", ""),
        "evidence": list(getattr(finding, "evidence", []) or []),
        "risk": getattr(finding, "risk", None),
        "recommended_actions": list(getattr(finding, "recommended_actions", []) or []),
        "status": getattr(finding, "status", ""),
    }


def _incident_payload(incident: Any) -> dict[str, Any]:
    return {
        "id": getattr(incident, "id", ""),
        "scenario_run_id": getattr(incident, "scenario_run_id", None),
        "incident_key": getattr(incident, "incident_key", ""),
        "title": getattr(incident, "title", ""),
        "severity": getattr(incident, "severity", ""),
        "status": getattr(incident, "status", ""),
        "finding_ids": list(getattr(incident, "finding_ids", []) or []),
        "summary": getattr(incident, "summary", None),
        "created_at": getattr(incident, "created_at", None),
        "updated_at": getattr(incident, "updated_at", None),
    }


def _mission_patch_payload(patch: Any | None) -> dict[str, Any] | None:
    if patch is None:
        return None
    return {
        "id": getattr(patch, "id", ""),
        "scenario_run_id": getattr(patch, "scenario_run_id", None),
        "incident_id": getattr(patch, "incident_id", None),
        "severity": getattr(patch, "severity", ""),
        "status": getattr(patch, "status", ""),
        "summary": getattr(patch, "summary", ""),
        "evidence": _safe_json(list(getattr(patch, "evidence", []) or [])),
        "actions": _safe_json(list(getattr(patch, "actions", []) or [])),
        "rollback_plan": _safe_json(getattr(patch, "rollback_plan", {}) or {}),
        "approval_required": bool(getattr(patch, "approval_required", False)),
        "created_by": getattr(patch, "created_by", None),
        "created_at": getattr(patch, "created_at", None),
        "updated_at": getattr(patch, "updated_at", None),
    }


def _approval_payload(approval: Any) -> dict[str, Any]:
    return {
        "id": getattr(approval, "id", ""),
        "scenario_run_id": getattr(approval, "scenario_run_id", None),
        "mission_patch_id": getattr(approval, "mission_patch_id", ""),
        "status": getattr(approval, "status", ""),
        "operator_id": getattr(approval, "operator_id", None),
        "operator_note": getattr(approval, "operator_note", None),
        "created_at": getattr(approval, "created_at", None),
        "decided_at": getattr(approval, "decided_at", None),
    }


def _command_payload(command: Any) -> dict[str, Any]:
    return {
        "id": getattr(command, "id", ""),
        "mission_patch_id": getattr(command, "mission_patch_id", ""),
        "action_type": getattr(command, "action_type", ""),
        "target_asset_id": getattr(command, "target_asset_id", None),
        "status": getattr(command, "status", ""),
        "input": _safe_json(getattr(command, "input", {}) or {}),
        "result": _safe_json(getattr(command, "result", {}) or {}),
        "created_at": getattr(command, "created_at", None),
        "updated_at": getattr(command, "updated_at", None),
    }


def _telemetry_event_payload(event: Any) -> dict[str, Any]:
    return {
        "id": getattr(event, "id", None),
        "scenario_run_id": getattr(event, "scenario_run_id", None),
        "event_type": getattr(event, "event_type", ""),
        "asset_id": getattr(event, "asset_id", None),
        "severity": getattr(event, "severity", ""),
        "payload": _safe_json(getattr(event, "payload", {}) or {}),
        "created_at": getattr(event, "created_at", None),
    }


def _world_snapshot_payload(snapshot: Any) -> dict[str, Any]:
    return {
        "id": getattr(snapshot, "id", ""),
        "scenario_run_id": getattr(snapshot, "scenario_run_id", None),
        "version": getattr(snapshot, "version", None),
        "state": _safe_json(getattr(snapshot, "state", {}) or {}),
        "reason": getattr(snapshot, "reason", ""),
        "created_by": getattr(snapshot, "created_by", ""),
        "created_at": getattr(snapshot, "created_at", None),
    }


def _context_summary(context: dict[str, Any]) -> dict[str, Any]:
    world = context["world"]
    patch = context["mission_patch"]
    findings = context["findings"]
    commands = context["commands"]
    return {
        "scenario": world.get("scenario_name") or world.get("scenario"),
        "world_version": world.get("version"),
        "agent_count": len(context["agents"]),
        "open_findings": sum(1 for finding in findings if finding.get("status") == "open"),
        "incident_count": len(context.get("incidents", [])),
        "mission_patch_count": len(context.get("mission_patches", [])),
        "command_count": len(commands),
        "queued_commands": sum(1 for command in commands if command.get("status") == "queued"),
        "running_commands": sum(1 for command in commands if command.get("status") == "running"),
        "succeeded_commands": sum(1 for command in commands if command.get("status") == "succeeded"),
        "active_patch_id": patch.get("id") if patch else None,
        "active_patch_status": patch.get("status") if patch else None,
    }


def _direct_operator_answer(message: str, context: dict[str, Any]) -> str | None:
    question = message.lower()
    world = context["world"]
    agents = context["agents"]
    findings = context["findings"]
    commands = context["commands"]
    patch = context["mission_patch"]
    satellite = world.get("satellite", {})
    power = world.get("power", {})
    thermal = world.get("thermal", {})
    radiation = world.get("radiation", {})
    downlink = world.get("downlink", {})
    training = world.get("training", {})
    nodes = world.get("nodes", [])

    node_metric = _targeted_node_metric_answer(question, nodes)
    if node_metric:
        return node_metric

    if any(term in question for term in ["altitude", "alt ", " alt", "height", "orbit height"]):
        return (
            "Orbit readout: "
            f"current altitude is {satellite.get('alt_km', '--')} km, "
            f"latitude is {satellite.get('lat', '--')}, longitude is {satellite.get('lon', '--')}, "
            f"velocity is {satellite.get('velocity_km_s', '--')} km/s, and orbit phase is "
            f"{satellite.get('orbit_phase', '--')}."
        )

    if any(term in question for term in ["eclipse", "battery", "power", "solar"]):
        return (
            "Power / orbit readout: "
            f"battery is {power.get('battery_percent', '--')}%, solar input is {power.get('solar_kw', '--')} kW, "
            f"compute budget is {power.get('compute_budget_kw', '--')} kW, and eclipse is in "
            f"{satellite.get('time_to_eclipse_min', '--')} min. "
            f"Current orbit phase is {satellite.get('orbit_phase', '--')} with ground link {satellite.get('ground_link', '--')}."
        )

    if any(term in question for term in ["thermal", "hotspot", "temperature", "temp", "cooling"]):
        targeted_temperature = _targeted_temperature_answer(question, nodes)
        if targeted_temperature:
            return targeted_temperature
        node_summary = _node_temperature_summary(nodes)
        return (
            "Thermal readout: "
            f"highest temperature is {thermal.get('highest_temp_c', '--')} C at {thermal.get('hotspot_node', '--')}; "
            f"cooling is {thermal.get('cooling_status', '--')}. {node_summary} "
            f"Node temperatures: {_node_temperature_list(nodes)}."
        )

    if any(term in question for term in ["radiation", "ecc", "xid", "checkpoint", "rollback", "nan"]):
        return (
            "Integrity readout: "
            f"radiation risk is {radiation.get('risk', '--')} in {radiation.get('region', '--')}; "
            f"ECC errors over 5 min: {radiation.get('ecc_errors_last_5min', '--')}; "
            f"Xid event: {'yes' if radiation.get('xid_event') else 'no'}. "
            f"Latest checkpoint {training.get('latest_checkpoint', '--')} is {training.get('latest_checkpoint_status', '--')}; "
            f"last trusted checkpoint is {training.get('last_trusted_checkpoint', '--')}."
        )

    if any(term in question for term in ["downlink", "ground", "transfer", "window"]):
        used = downlink.get("used_gb", "--")
        capacity = downlink.get("capacity_gb", "--")
        open_label = "open" if downlink.get("window_open") else "closed"
        return (
            "Downlink readout: "
            f"window is {open_label}, capacity is {capacity} GB, used is {used} GB, "
            f"time remaining is {downlink.get('time_remaining_min', '--')} min."
        )

    if any(term in question for term in ["patch", "approve", "approval", "propose", "command", "action"]):
        if not patch:
            if commands:
                command_text = ", ".join(
                    f"{command.get('action_type', 'command')}={command.get('status', 'unknown')}"
                    for command in commands[:5]
                )
                return f"No active mission patch is awaiting action. Recent command status: {command_text}."
            return "No active mission patch is currently awaiting action. Agents are monitoring and will surface a patch when findings converge."
        actions = ", ".join(_action_label(action) for action in patch.get("actions", [])[:5]) or "no commands attached"
        return (
            f"Active mission patch {patch.get('id')} is {patch.get('status')}: {patch.get('summary')} "
            f"Validated actions: {actions}. Approval required: {'yes' if patch.get('approval_required') else 'no'}."
        )

    if any(term in question for term in ["critical", "severe", "most important", "priority", "worst"]):
        top_finding = findings[0] if findings else None
        top_agent = agents[0] if agents else None
        if top_finding:
            return (
                f"Highest priority finding is from {top_finding.get('agent_name')}: "
                f"{top_finding.get('finding')} ({top_finding.get('severity')}, "
                f"{round(float(top_finding.get('confidence') or 0) * 100)}% confidence). "
                f"Risk: {top_finding.get('risk') or 'not specified'}."
            )
        if top_agent:
            return (
                f"Highest priority agent is {top_agent.get('display_name')}: "
                f"{top_agent.get('message')} ({top_agent.get('severity')}, {top_agent.get('phase')})."
            )

    return _generic_data_lookup_answer(question, context)


def _fallback_operator_answer(message: str, context: dict[str, Any]) -> str:
    direct = _direct_operator_answer(message, context)
    if direct:
        return _bounded(direct, MAX_REPLY_CHARS)

    question = message.lower()
    world = context["world"]
    agents = context["agents"]
    findings = context["findings"]
    commands = context["commands"]
    patch = context["mission_patch"]
    satellite = world.get("satellite", {})
    power = world.get("power", {})
    thermal = world.get("thermal", {})
    radiation = world.get("radiation", {})
    downlink = world.get("downlink", {})
    training = world.get("training", {})
    nodes = world.get("nodes", [])

    if any(term in question for term in ["altitude", "alt ", " alt", "height", "orbit height"]):
        return _bounded(
            "Orbit readout: "
            f"current altitude is {satellite.get('alt_km', '--')} km, "
            f"latitude is {satellite.get('lat', '--')}, longitude is {satellite.get('lon', '--')}, "
            f"velocity is {satellite.get('velocity_km_s', '--')} km/s, and orbit phase is "
            f"{satellite.get('orbit_phase', '--')}.",
            MAX_REPLY_CHARS,
        )

    if any(term in question for term in ["eclipse", "battery", "power", "solar"]):
        return _bounded(
            "Power / orbit readout: "
            f"battery is {power.get('battery_percent', '--')}%, solar input is {power.get('solar_kw', '--')} kW, "
            f"compute budget is {power.get('compute_budget_kw', '--')} kW, and eclipse is in "
            f"{satellite.get('time_to_eclipse_min', '--')} min. "
            f"Current orbit phase is {satellite.get('orbit_phase', '--')} with ground link {satellite.get('ground_link', '--')}.",
            MAX_REPLY_CHARS,
        )

    if any(term in question for term in ["thermal", "hotspot", "temperature", "temp", "cooling"]):
        targeted_temperature = _targeted_temperature_answer(question, nodes)
        if targeted_temperature:
            return _bounded(targeted_temperature, MAX_REPLY_CHARS)
        node_summary = _node_temperature_summary(nodes)
        return _bounded(
            "Thermal readout: "
            f"highest temperature is {thermal.get('highest_temp_c', '--')} C at {thermal.get('hotspot_node', '--')}; "
            f"cooling is {thermal.get('cooling_status', '--')}. {node_summary} "
            f"Node temperatures: {_node_temperature_list(nodes)}.",
            MAX_REPLY_CHARS,
        )

    if any(term in question for term in ["radiation", "ecc", "xid", "checkpoint", "rollback", "nan"]):
        return _bounded(
            "Integrity readout: "
            f"radiation risk is {radiation.get('risk', '--')} in {radiation.get('region', '--')}; "
            f"ECC errors over 5 min: {radiation.get('ecc_errors_last_5min', '--')}; "
            f"Xid event: {'yes' if radiation.get('xid_event') else 'no'}. "
            f"Latest checkpoint {training.get('latest_checkpoint', '--')} is {training.get('latest_checkpoint_status', '--')}; "
            f"last trusted checkpoint is {training.get('last_trusted_checkpoint', '--')}.",
            MAX_REPLY_CHARS,
        )

    if any(term in question for term in ["downlink", "ground", "transfer", "window"]):
        used = downlink.get("used_gb", "--")
        capacity = downlink.get("capacity_gb", "--")
        open_label = "open" if downlink.get("window_open") else "closed"
        return _bounded(
            "Downlink readout: "
            f"window is {open_label}, capacity is {capacity} GB, used is {used} GB, "
            f"time remaining is {downlink.get('time_remaining_min', '--')} min.",
            MAX_REPLY_CHARS,
        )

    if any(term in question for term in ["patch", "approve", "approval", "propose", "command", "action"]):
        if not patch:
            if commands:
                command_text = ", ".join(
                    f"{command.get('action_type', 'command')}={command.get('status', 'unknown')}"
                    for command in commands[:5]
                )
                return _bounded(
                    f"No active mission patch is awaiting action. Recent command status: {command_text}.",
                    MAX_REPLY_CHARS,
                )
            return "No active mission patch is currently awaiting action. Agents are monitoring and will surface a patch when findings converge."
        actions = ", ".join(_action_label(action) for action in patch.get("actions", [])[:5]) or "no commands attached"
        return _bounded(
            f"Active mission patch {patch.get('id')} is {patch.get('status')}: {patch.get('summary')} "
            f"Validated actions: {actions}. Approval required: {'yes' if patch.get('approval_required') else 'no'}.",
            MAX_REPLY_CHARS,
        )

    if any(term in question for term in ["critical", "severe", "most important", "priority", "worst"]):
        top_finding = findings[0] if findings else None
        top_agent = agents[0] if agents else None
        if top_finding:
            return _bounded(
                f"Highest priority finding is from {top_finding.get('agent_name')}: "
                f"{top_finding.get('finding')} ({top_finding.get('severity')}, "
                f"{round(float(top_finding.get('confidence') or 0) * 100)}% confidence). "
                f"Risk: {top_finding.get('risk') or 'not specified'}.",
                MAX_REPLY_CHARS,
            )
        if top_agent:
            return _bounded(
                f"Highest priority agent is {top_agent.get('display_name')}: "
                f"{top_agent.get('message')} ({top_agent.get('severity')}, {top_agent.get('phase')}).",
                MAX_REPLY_CHARS,
            )

    open_findings = [finding for finding in findings if finding.get("status") == "open"]
    top_agent = agents[0] if agents else None
    patch_text = (
        f"Active patch {patch.get('id')} is {patch.get('status')}. "
        if patch
        else "No active mission patch. "
    )
    agent_text = (
        f"Most urgent agent: {top_agent.get('display_name')} says {top_agent.get('message')}"
        if top_agent
        else "Agent status has not loaded yet."
    )
    return _bounded(
        f"Mission snapshot: {world.get('scenario_name') or world.get('scenario') or 'current scenario'}, "
        f"{len(open_findings)} open finding(s). {patch_text}{agent_text}",
        MAX_REPLY_CHARS,
    )


def _node_temperature_summary(nodes: list[Any]) -> str:
    normalized = [node for node in nodes if isinstance(node, dict)]
    if not normalized:
        return "No node-level temperatures are available."
    hottest = max(normalized, key=lambda node: float(node.get("temp_c") or 0))
    return f"Hottest node is {hottest.get('id', '--')} at {hottest.get('temp_c', '--')} C."


def _targeted_node_metric_answer(question: str, nodes: list[Any]) -> str | None:
    normalized_nodes = [node for node in nodes if isinstance(node, dict)]
    if not normalized_nodes:
        return None
    target = _extract_node_or_rack_target(question)
    if target is None:
        return None

    metric = _requested_node_metric(question)
    if metric is None:
        return None

    for node in normalized_nodes:
        node_id = str(node.get("id") or "").lower()
        aliases = _node_aliases(node_id, normalized_nodes)
        if target not in aliases:
            continue
        value = node.get(metric["key"], "--")
        label = metric["label"]
        unit = metric["unit"]
        status = node.get("status", "unknown")
        suffix = f" {unit}" if unit and value != "--" else ""
        rack_note = " Rack-level telemetry is represented by node sensors in the current backend state."
        return f"{node.get('id', target)} {label} is {value}{suffix}; status is {status}.{rack_note}"
    return None


def _requested_node_metric(question: str) -> dict[str, str] | None:
    metric_map = [
        (["temperature", "temp", "thermal"], {"key": "temp_c", "label": "temperature", "unit": "C"}),
        (["gpu", "util", "utilization", "load"], {"key": "gpu_util", "label": "GPU utilization", "unit": "%"}),
        (["power", "watt", "watts"], {"key": "power_w", "label": "power draw", "unit": "W"}),
        (["rank", "lag"], {"key": "rank_lag", "label": "rank lag", "unit": ""}),
        (["ecc", "error", "errors"], {"key": "ecc_errors", "label": "ECC errors", "unit": ""}),
        (["xid"], {"key": "xid_event", "label": "Xid event", "unit": ""}),
        (["vibration"], {"key": "vibration_score", "label": "vibration score", "unit": ""}),
        (["status", "state", "health"], {"key": "status", "label": "status", "unit": ""}),
    ]
    for terms, metric in metric_map:
        if any(term in question for term in terms):
            return metric
    return None


def _targeted_temperature_answer(question: str, nodes: list[Any]) -> str | None:
    normalized_nodes = [node for node in nodes if isinstance(node, dict)]
    if not normalized_nodes:
        return None

    target = _extract_node_or_rack_target(question)
    if target is None:
        return None

    for node in normalized_nodes:
        node_id = str(node.get("id") or "").lower()
        aliases = _node_aliases(node_id, normalized_nodes)
        if target in aliases:
            temp = node.get("temp_c", "--")
            status = node.get("status", "unknown")
            rack_note = " Rack-level telemetry is represented by node sensors in the current backend state."
            return f"{node.get('id', target)} temperature is {temp} C; status is {status}.{rack_note}"

    return (
        f"I do not have telemetry for {target}. Available node temperatures: "
        f"{_node_temperature_list(normalized_nodes)}."
    )


def _extract_node_or_rack_target(question: str) -> str | None:
    patterns = [
        r"\bnode[-\s]?([a-z0-9]+)\b",
        r"\brack[-\s]?([a-z0-9]+)\b",
        r"\b([a-z0-9])[-\s]?rack\b",
        r"\br([0-9]+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, question)
        if not match:
            continue
        raw = match.group(1).lower()
        if pattern == r"\br([0-9]+)\b":
            return f"rack-{raw}"
        if raw.startswith("node-"):
            return raw
        return f"node-{raw}" if not raw.isdigit() else f"rack-{raw}"
    return None


def _node_aliases(node_id: str, nodes: list[dict[str, Any]]) -> set[str]:
    aliases = {node_id, node_id.replace("-", " ")}
    suffix = node_id.removeprefix("node-")
    if suffix and suffix != node_id:
        aliases.update({f"node-{suffix}", f"node {suffix}", f"rack-{suffix}", f"rack {suffix}"})

    ordered_ids = [str(node.get("id") or "").lower() for node in nodes]
    try:
        index = ordered_ids.index(node_id) + 1
    except ValueError:
        index = 0
    if index:
        aliases.update({f"rack-{index}", f"rack {index}", f"r{index}"})
    return aliases


def _node_temperature_list(nodes: list[Any]) -> str:
    normalized = [node for node in nodes if isinstance(node, dict)]
    if not normalized:
        return "none available"
    return ", ".join(f"{node.get('id', 'unknown')}={node.get('temp_c', '--')} C" for node in normalized)


def _generic_data_lookup_answer(question: str, context: dict[str, Any]) -> str | None:
    tokens = _query_tokens(question)
    if not tokens:
        return None

    rows = _flatten_for_lookup(context.get("all_accessible_data", {}))
    scored: list[tuple[int, str, Any]] = []
    for path, value in rows:
        searchable = _normalize_lookup_text(path)
        score = sum(1 for token in tokens if token in searchable)
        if score:
            scored.append((score, path, value))

    if not scored:
        return None
    scored.sort(key=lambda row: (-row[0], len(row[1])))
    best_score = scored[0][0]
    if best_score < 2 and len(tokens) > 1:
        return None

    matches = []
    seen_paths: set[str] = set()
    for _score, path, value in scored:
        if path in seen_paths:
            continue
        seen_paths.add(path)
        matches.append(f"{path} = {_format_lookup_value(value)}")
        if len(matches) >= 5:
            break
    return "Matching backend data: " + "; ".join(matches) + "."


def _flatten_for_lookup(value: Any, path: str = "data") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        rows: list[tuple[str, Any]] = []
        for key, child in value.items():
            if key == "all_accessible_data":
                continue
            child_path = f"{path}.{key}"
            rows.extend(_flatten_for_lookup(child, child_path))
        return rows
    if isinstance(value, list):
        rows = []
        for index, item in enumerate(value):
            identifier = _record_identifier(item)
            child_path = f"{path}[{identifier or index}]"
            rows.extend(_flatten_for_lookup(item, child_path))
        return rows
    if value is None or isinstance(value, bool | int | float | str):
        return [(path, value)]
    return [(path, str(value))]


def _record_identifier(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("event_type", "agent", "agent_name", "incident_key", "mission_patch_id", "id", "status"):
        candidate = value.get(key)
        if isinstance(candidate, str | int | float) and str(candidate):
            return str(candidate)
    return None


def _query_tokens(question: str) -> list[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "at",
        "be",
        "current",
        "for",
        "from",
        "give",
        "how",
        "in",
        "is",
        "me",
        "of",
        "on",
        "show",
        "tell",
        "the",
        "to",
        "what",
        "whats",
        "which",
    }
    aliases = {
        "temperature": ["temp", "temp_c"],
        "temp": ["temperature", "temp_c"],
        "battery": ["battery_percent"],
        "altitude": ["alt_km"],
        "velocity": ["velocity_km_s"],
        "checkpoint": ["latest_checkpoint", "last_trusted_checkpoint"],
        "gpu": ["gpu_util"],
        "utilization": ["gpu_util"],
        "ecc": ["ecc_errors", "ecc_errors_last_5min"],
    }
    raw_tokens = [token for token in re.findall(r"[a-z0-9_]+", question.lower()) if token not in stopwords and len(token) > 1]
    expanded: list[str] = []
    for token in raw_tokens:
        expanded.append(token)
        expanded.extend(aliases.get(token, []))
    return list(dict.fromkeys(expanded))


def _normalize_lookup_text(value: str) -> str:
    return value.lower().replace("-", "_").replace("[", "_").replace("]", "_").replace(".", "_")


def _format_lookup_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "unknown"
    return str(value)


def _action_label(action: Any) -> str:
    if not isinstance(action, dict):
        return str(action)
    action_type = str(action.get("type", "action")).replace("_", " ")
    target = action.get("node_id") or action.get("job_id") or action.get("checkpoint_id") or action.get("target_asset_id")
    return f"{action_type} ({target})" if target else action_type


def _severity_rank(value: str) -> int:
    return SEVERITY_RANK.get(str(value).upper(), 99)


def _bounded(value: str, max_chars: int) -> str:
    text = " ".join(value.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _numeric_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, child in value.items():
            if key in {"image_data_url", "audio_data_url", "idempotency_key"}:
                safe[key] = _omitted_value(child)
            else:
                safe[key] = _safe_json(child)
        return safe
    if isinstance(value, list):
        return [_safe_json(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_json(item) for item in value]
    return value


def _omitted_value(value: Any) -> str:
    if isinstance(value, str):
        return f"<omitted {len(value)} chars>"
    return "<omitted>"
