"""Mission-aware operator chatbot service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.schemas.chat import ChatTurn
from app.services.llm_client import answer_operator_chat


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
) -> OperatorChatReply:
    context = _context_payload(world_state, agents, findings, commands or [], mission_patch)
    model_reply = await answer_operator_chat(message=message, history=history, context=context)
    if model_reply:
        return OperatorChatReply(
            content=_bounded(model_reply, MAX_REPLY_CHARS),
            source="crusoe",
            model=settings.crusoe_model,
            context_summary=_context_summary(context),
        )

    return OperatorChatReply(
        content=_fallback_operator_answer(message, context),
        source="deterministic",
        model=None,
        context_summary=_context_summary(context),
    )


def _context_payload(
    world_state: Any | None,
    agents: list[Any],
    findings: list[Any],
    commands: list[Any],
    mission_patch: Any | None,
) -> dict[str, Any]:
    state = getattr(world_state, "state", None) or {}
    sorted_agents = sorted(agents, key=lambda item: _severity_rank(getattr(item, "severity", "")))
    sorted_findings = sorted(
        findings,
        key=lambda item: (
            _severity_rank(getattr(item, "severity", "")),
            str(getattr(item, "created_at", "")),
        ),
    )
    sorted_commands = sorted(commands, key=lambda item: str(getattr(item, "created_at", "")), reverse=True)

    return {
        "world": {
            "version": getattr(world_state, "version", None),
            "scenario_run_id": getattr(world_state, "scenario_run_id", None),
            "scenario": state.get("scenario"),
            "scenario_name": state.get("scenario_name"),
            "satellite": state.get("satellite", {}),
            "power": state.get("power", {}),
            "thermal": state.get("thermal", {}),
            "radiation": state.get("radiation", {}),
            "downlink": state.get("downlink", {}),
            "training": state.get("training", {}),
            "nodes": state.get("nodes", []),
        },
        "agents": [_agent_payload(agent) for agent in sorted_agents],
        "findings": [_finding_payload(finding) for finding in sorted_findings[:8]],
        "commands": [_command_payload(command) for command in sorted_commands[:12]],
        "mission_patch": _mission_patch_payload(mission_patch),
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


def _mission_patch_payload(patch: Any | None) -> dict[str, Any] | None:
    if patch is None:
        return None
    return {
        "id": getattr(patch, "id", ""),
        "incident_id": getattr(patch, "incident_id", None),
        "severity": getattr(patch, "severity", ""),
        "status": getattr(patch, "status", ""),
        "summary": getattr(patch, "summary", ""),
        "evidence": list(getattr(patch, "evidence", []) or []),
        "actions": list(getattr(patch, "actions", []) or []),
        "rollback_plan": getattr(patch, "rollback_plan", {}) or {},
        "approval_required": bool(getattr(patch, "approval_required", False)),
    }


def _command_payload(command: Any) -> dict[str, Any]:
    return {
        "id": getattr(command, "id", ""),
        "mission_patch_id": getattr(command, "mission_patch_id", ""),
        "action_type": getattr(command, "action_type", ""),
        "target_asset_id": getattr(command, "target_asset_id", None),
        "status": getattr(command, "status", ""),
        "input": getattr(command, "input", {}) or {},
        "result": getattr(command, "result", {}) or {},
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
        "command_count": len(commands),
        "queued_commands": sum(1 for command in commands if command.get("status") == "queued"),
        "running_commands": sum(1 for command in commands if command.get("status") == "running"),
        "succeeded_commands": sum(1 for command in commands if command.get("status") == "succeeded"),
        "active_patch_id": patch.get("id") if patch else None,
        "active_patch_status": patch.get("status") if patch else None,
    }


def _fallback_operator_answer(message: str, context: dict[str, Any]) -> str:
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
        node_summary = _node_temperature_summary(world.get("nodes", []))
        return _bounded(
            "Thermal readout: "
            f"highest temperature is {thermal.get('highest_temp_c', '--')} C at {thermal.get('hotspot_node', '--')}; "
            f"cooling is {thermal.get('cooling_status', '--')}. {node_summary}",
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
