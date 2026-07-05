"""Optional Crusoe/Nemotron integrations for agent evidence interpretation."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.config import settings
from app.services.agent_prompts import (
    AGENT_ACTION_ALLOWLISTS,
    agent_analysis_system_prompt,
    commander_summary_messages,
)


NEMOTRON_OMNI_MODEL = "nvidia/Nemotron-3-Nano-Omni-Reasoning-30B-A3B"
MAX_MISSION_SUMMARY_CHARS = 900
MAX_OPERATOR_CHAT_CHARS = 1400
MAX_AGENT_ANALYSIS_CHARS = 900


async def polish_mission_patch_summary(summary: str, context: dict) -> str:
    """Return deterministic text unless Crusoe is explicitly enabled.

    The hackathon backend must boot without external credentials. The Commander
    still owns deterministic actions and safety; this hook is only for future
    wording polish when `CRUSOE_ENABLED=true` and credentials are present.
    """
    if not settings.crusoe_enabled or not settings.crusoe_api_key:
        return summary
    response = await _crusoe_chat_completion(
        model=settings.crusoe_model,
        messages=commander_summary_messages(summary, context),
        max_tokens=256,
        temperature=0.2,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    content = _message_content(response)
    return _bounded_text(content, MAX_MISSION_SUMMARY_CHARS) if content else _bounded_text(summary, MAX_MISSION_SUMMARY_CHARS)


async def answer_operator_chat(
    *,
    message: str,
    history: list[Any],
    context: dict[str, Any],
) -> str:
    """Answer operator chat from current backend mission context.

    Returns an empty string when Crusoe is not configured so callers can use a
    deterministic fallback. The model is advisory only; it cannot approve or
    execute mission patches.
    """
    if not settings.crusoe_enabled or not settings.crusoe_api_key:
        return ""

    prompt = build_operator_chat_prompt(message=message, context=context)
    recent_history = [
        {
            "role": "assistant" if getattr(turn, "role", "") == "assistant" else "user",
            "content": _bounded_text(getattr(turn, "content", ""), 700),
        }
        for turn in history[-8:]
        if getattr(turn, "content", "").strip()
    ]
    response = await _crusoe_chat_completion(
        model=settings.crusoe_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are OrbitOps, a concise mission-control chatbot for an orbital GPU data center. "
                    "Answer only from the named mission variables in the current prompt. "
                    "Be operational, concrete, and brief. Cite specific variable names or asset IDs when useful. "
                    "If a variable is null or absent, say the value is unknown instead of guessing. "
                    "Do not claim to approve, reject, execute, or schedule commands. If action is needed, "
                    "state that the human operator must use the mission patch controls."
                ),
            },
            *recent_history,
            {
                "role": "user",
                "content": prompt,
            },
        ],
        max_tokens=420,
        temperature=0.2,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    return _bounded_text(_message_content(response), MAX_OPERATOR_CHAT_CHARS)


def build_operator_chat_prompt(*, message: str, context: dict[str, Any]) -> str:
    """Render explicit mission variables for the operator chatbot prompt."""
    variables = build_operator_chat_variables(context)
    priority_lines = [
        ("scenario_name", variables.get("scenario_name")),
        ("world_version", variables.get("world_version")),
        ("orbit_phase", variables.get("orbit_phase")),
        ("time_to_eclipse_min", variables.get("time_to_eclipse_min")),
        ("battery_percent", variables.get("battery_percent")),
        ("thermal_highest_temp_c", variables.get("thermal_highest_temp_c")),
        ("thermal_hotspot_node", variables.get("thermal_hotspot_node")),
        ("radiation_level", variables.get("radiation_level")),
        ("radiation_ecc_errors_last_5min", variables.get("radiation_ecc_errors_last_5min")),
        ("downlink_capacity_gb", variables.get("downlink_capacity_gb")),
        ("training_latest_checkpoint_status", variables.get("training_latest_checkpoint_status")),
        ("active_patch_status", variables.get("active_patch_status")),
        ("open_findings_count", variables.get("open_findings_count")),
        ("command_status_counts", variables.get("command_status_counts")),
    ]
    summary = "\n".join(f"- {key}={json.dumps(value, default=str)}" for key, value in priority_lines)
    return (
        "Use the following named variables as the complete source of truth for this answer. "
        "Prefer the flattened variable names for direct mission facts, and use the arrays for supporting detail.\n\n"
        "PRIORITY_VARIABLES:\n"
        f"{summary}\n\n"
        "MISSION_VARIABLES_JSON:\n"
        f"{json.dumps(variables, default=str, sort_keys=True)}\n\n"
        "ANSWER_RULES:\n"
        "- Use only the values above.\n"
        "- Keep the answer concise and operator-focused.\n"
        "- Mention the relevant agent, asset, mission patch, command, or checkpoint when the variables contain it.\n"
        "- Do not approve, reject, execute, schedule, or imply command authority.\n\n"
        f"OPERATOR_QUESTION={message}"
    )


def build_operator_chat_variables(context: dict[str, Any]) -> dict[str, Any]:
    """Flatten mission context into explicit variables the model can reason over."""
    world = _mapping(context.get("world"))
    satellite = _mapping(world.get("satellite"))
    power = _mapping(world.get("power"))
    thermal = _mapping(world.get("thermal"))
    radiation = _mapping(world.get("radiation"))
    computed_radiation = _mapping(radiation.get("computed_risk"))
    downlink = _mapping(world.get("downlink"))
    training = _mapping(world.get("training"))
    nodes = _sequence(world.get("nodes"))
    agents = _sequence(context.get("agents"))
    findings = _sequence(context.get("findings"))
    commands = _sequence(context.get("commands"))
    patch = _mapping(context.get("mission_patch"))
    patch_actions = _sequence(patch.get("actions")) if patch else []

    open_findings = [finding for finding in findings if _mapping(finding).get("status") == "open"]
    attention_agents = [
        agent
        for agent in agents
        if str(_mapping(agent).get("severity", "")).upper() not in {"", "INFO"}
        or str(_mapping(agent).get("status", "")).lower() not in {"", "monitoring", "healthy"}
    ]

    return {
        "scenario_name": world.get("scenario_name") or world.get("scenario"),
        "scenario_run_id": world.get("scenario_run_id"),
        "world_version": world.get("version"),
        "satellite_id": satellite.get("id"),
        "satellite_lat": satellite.get("lat"),
        "satellite_lon": satellite.get("lon"),
        "satellite_alt_km": satellite.get("alt_km"),
        "orbit_phase": satellite.get("orbit_phase"),
        "time_to_eclipse_min": satellite.get("time_to_eclipse_min"),
        "ground_link": satellite.get("ground_link"),
        "battery_percent": power.get("battery_percent"),
        "solar_kw": power.get("solar_kw"),
        "compute_budget_kw": power.get("compute_budget_kw"),
        "cooling_power_kw": power.get("cooling_power_kw"),
        "comms_power_kw": power.get("comms_power_kw"),
        "power_mode": power.get("mode"),
        "thermal_highest_temp_c": thermal.get("highest_temp_c"),
        "thermal_hotspot_node": thermal.get("hotspot_node"),
        "thermal_cooling_status": thermal.get("cooling_status"),
        "thermal_latest_visual_input": _compact_visual_input(_mapping(thermal.get("latest_visual_input"))),
        "radiation_risk": radiation.get("risk"),
        "radiation_region": radiation.get("region"),
        "radiation_ecc_errors_last_5min": radiation.get("ecc_errors_last_5min"),
        "radiation_xid_event": radiation.get("xid_event"),
        "radiation_score": computed_radiation.get("radiationRiskScore"),
        "radiation_level": computed_radiation.get("radiationLevel") or radiation.get("risk"),
        "radiation_main_cause": computed_radiation.get("mainCause"),
        "radiation_recommended_action": computed_radiation.get("recommendedAction"),
        "radiation_explanation": computed_radiation.get("explanation"),
        "downlink_window_open": downlink.get("window_open"),
        "downlink_capacity_gb": downlink.get("capacity_gb"),
        "downlink_used_gb": downlink.get("used_gb"),
        "downlink_time_remaining_min": downlink.get("time_remaining_min"),
        "training_job_id": training.get("job_id"),
        "training_status": training.get("status"),
        "training_current_step": training.get("current_step"),
        "training_last_trusted_checkpoint": training.get("last_trusted_checkpoint"),
        "training_latest_checkpoint": training.get("latest_checkpoint"),
        "training_latest_checkpoint_status": training.get("latest_checkpoint_status"),
        "training_loss_state": training.get("loss_state"),
        "node_count": len(nodes),
        "nodes": _compact_nodes(nodes),
        "agent_count": len(agents),
        "agents": _compact_agents(agents),
        "agents_needing_attention": _compact_agents(attention_agents),
        "highest_priority_agent": _compact_agent(attention_agents[0]) if attention_agents else _compact_agent(agents[0]) if agents else None,
        "open_findings_count": len(open_findings),
        "findings": _compact_findings(findings),
        "highest_priority_finding": _compact_finding(open_findings[0]) if open_findings else _compact_finding(findings[0]) if findings else None,
        "active_patch_id": patch.get("id") if patch else None,
        "active_patch_status": patch.get("status") if patch else None,
        "active_patch_severity": patch.get("severity") if patch else None,
        "active_patch_summary": patch.get("summary") if patch else None,
        "active_patch_approval_required": patch.get("approval_required") if patch else None,
        "active_patch_action_count": len(patch_actions),
        "active_patch_actions": [_compact_action(action) for action in patch_actions],
        "active_patch_rollback_plan": patch.get("rollback_plan") if patch else None,
        "command_count": len(commands),
        "command_status_counts": _status_counts(commands),
        "commands": _compact_commands(commands),
        "approval_boundary": (
            "The AI can explain mission context and recommend operator review, but only the human operator "
            "can approve, reject, modify, or execute mission patch controls."
        ),
    }


async def analyze_agent_finding(
    *,
    agent_name: str,
    state: dict[str, Any],
    finding: dict[str, Any],
) -> dict[str, Any] | None:
    """Ask Crusoe for advisory analysis of a triggered agent finding.

    The model can refine the explanation and propose allowed follow-up actions,
    but deterministic code still detects the condition, builds executable
    commands, validates safety, and requires human approval before execution.
    """
    if not settings.crusoe_enabled or not settings.crusoe_api_key or not settings.crusoe_agent_analysis_enabled:
        return None

    allowed_actions = sorted(AGENT_ACTION_ALLOWLISTS.get(agent_name, set(finding.get("recommended_actions") or [])))
    started_at = time.perf_counter()
    response = await _crusoe_chat_completion(
        model=settings.crusoe_model,
        messages=[
            {
                "role": "system",
                "content": agent_analysis_system_prompt(agent_name),
            },
            {
                "role": "user",
                "content": (
                    "Analyze this triggered finding using the JSON contract from your instructions.\n\n"
                    f"Allowed actions: {json.dumps(allowed_actions)}\n"
                    f"Runtime context JSON: {json.dumps(_agent_context(agent_name, state), default=str, sort_keys=True)}\n"
                    f"Deterministic finding JSON: {json.dumps(finding, default=str, sort_keys=True)}"
                ),
            },
        ],
        max_tokens=640,
        temperature=0.2,
        response_format={"type": "json_object"},
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    parsed = _parse_json_object(_message_content(response, include_reasoning=True))
    if not parsed:
        return None
    analysis = _normalize_agent_analysis(parsed, allowed_actions)
    analysis["latency_ms"] = latency_ms
    return analysis


async def analyze_thermal_ir_image(
    image_data_url: str,
    *,
    state: dict[str, Any],
    finding: dict[str, Any],
) -> dict[str, Any] | None:
    """Ask Nemotron Omni to interpret a thermal IR frame for the thermal agent.

    Deterministic thresholds still decide the finding and executable actions.
    The model is used as a perception/evidence layer for image-specific detail:
    visible hotspot pattern, likely affected asset, operator-readable
    explanation, and follow-up questions only when the audit fails.
    """
    if not image_data_url.startswith("data:image/"):
        return None

    prompt = {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": image_data_url}},
            {
                "type": "text",
                "text": (
                    "You are the thermal/physical inspection sub-agent for an orbital GPU data center. "
                    "Analyze the attached thermal IR image against the current telemetry and finding. "
                    "Return only a JSON object with keys: audit_verdict, summary, confidence, affected_assets, "
                    "evidence, risk, recommended_actions, questions, needs_human_review. audit_verdict must be "
                    "pass, warn, or fail. Use fail only when the image or telemetry does not support the "
                    "deterministic finding, critical data is missing, or confidence is too low for operator use. "
                    "Only fail may include operator questions or additional recommended_actions; pass and warn "
                    "must use empty questions and recommended_actions arrays. Keep recommendations within this "
                    f"allowlist: {', '.join(sorted(AGENT_ACTION_ALLOWLISTS['thermal_physical_agent']))}. "
                    "Do not invent assets outside the telemetry.\n\n"
                    f"Telemetry JSON: {json.dumps(_thermal_context(state), sort_keys=True)}\n"
                    f"Deterministic finding JSON: {json.dumps(finding, sort_keys=True)}"
                ),
            },
        ],
    }
    started_at = time.perf_counter()
    response = await _crusoe_chat_completion(
        model=settings.crusoe_multimodal_model or NEMOTRON_OMNI_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You interpret multimodal evidence for a safety-critical agent. "
                    "Never approve actions; only explain observed evidence and uncertainty."
                ),
            },
            prompt,
        ],
        max_tokens=1024,
        temperature=0.2,
        response_format={"type": "json_object"},
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    parsed = _parse_json_object(_message_content(response, include_reasoning=True))
    if not parsed:
        return None
    analysis = _normalize_thermal_analysis(parsed)
    analysis["latency_ms"] = latency_ms
    return analysis


async def _crusoe_chat_completion(
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    response_format: dict[str, Any] | None = None,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not settings.crusoe_enabled or not settings.crusoe_api_key:
        return None

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    if extra_body:
        payload.update(extra_body)

    url = f"{settings.crusoe_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.crusoe_api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        return None


def _message_content(response: dict[str, Any] | None, *, include_reasoning: bool = False) -> str:
    if not response:
        return ""
    choices = response.get("choices") or []
    if not choices:
        return ""
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        text = "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict)).strip()
        if text:
            return text
    if include_reasoning:
        message = choices[0].get("message") or {}
        reasoning = message.get("reasoning") or message.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning
    return ""


def _bounded_text(value: str, max_chars: int) -> str:
    text = " ".join(value.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _parse_json_object(content: str) -> dict[str, Any] | None:
    if not content:
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sequence(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact_visual_input(value: dict[str, Any]) -> dict[str, Any] | None:
    if not value:
        return None
    model_result = _mapping(value.get("model_result"))
    return {
        "id": value.get("id"),
        "asset_id": value.get("asset_id"),
        "source": value.get("source"),
        "notes": value.get("notes"),
        "received_at": value.get("received_at"),
        "analysis_status": value.get("analysis_status"),
        "model_summary": model_result.get("summary"),
        "model_verdict": model_result.get("audit_verdict"),
        "model_confidence": model_result.get("confidence"),
        "model_needs_human_review": model_result.get("needs_human_review"),
    }


def _compact_nodes(nodes: list[Any]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for node in nodes[:12]:
        item = _mapping(node)
        if not item:
            continue
        compacted.append(
            {
                "id": item.get("id"),
                "status": item.get("status"),
                "gpu_util": item.get("gpu_util"),
                "temp_c": item.get("temp_c"),
                "power_w": item.get("power_w"),
                "rank_lag": item.get("rank_lag"),
                "ecc_errors": item.get("ecc_errors"),
                "xid_event": item.get("xid_event"),
                "vibration_score": item.get("vibration_score"),
            }
        )
    return compacted


def _compact_agents(agents: list[Any]) -> list[dict[str, Any]]:
    return [_compact_agent(agent) for agent in agents[:12]]


def _compact_agent(agent: Any) -> dict[str, Any]:
    item = _mapping(agent)
    return {
        "agent": item.get("agent"),
        "display_name": item.get("display_name"),
        "status": item.get("status"),
        "phase": item.get("phase"),
        "severity": item.get("severity"),
        "message": item.get("message"),
        "linked_mission_patch_id": item.get("linked_mission_patch_id"),
    }


def _compact_findings(findings: list[Any]) -> list[dict[str, Any]]:
    return [_compact_finding(finding) for finding in findings[:8]]


def _compact_finding(finding: Any) -> dict[str, Any]:
    item = _mapping(finding)
    return {
        "id": item.get("id"),
        "agent_name": item.get("agent_name"),
        "severity": item.get("severity"),
        "confidence": item.get("confidence"),
        "affected_assets": _sequence(item.get("affected_assets")),
        "finding": item.get("finding"),
        "evidence": _sequence(item.get("evidence"))[:6],
        "risk": item.get("risk"),
        "recommended_actions": _sequence(item.get("recommended_actions")),
        "status": item.get("status"),
    }


def _compact_action(action: Any) -> dict[str, Any]:
    if action is None:
        return {}
    if not isinstance(action, dict):
        return {"type": str(action)}
    item = _mapping(action)
    if not item:
        return {}
    return {
        key: item.get(key)
        for key in (
            "type",
            "node_id",
            "job_id",
            "checkpoint_id",
            "target_asset_id",
            "asset_id",
            "asset_ids",
            "scope",
            "reason",
            "power_percent",
            "interval_minutes",
            "send_first",
            "defer",
            "include",
        )
        if key in item
    }


def _compact_commands(commands: list[Any]) -> list[dict[str, Any]]:
    return [_compact_command(command) for command in commands[:12]]


def _compact_command(command: Any) -> dict[str, Any]:
    item = _mapping(command)
    return {
        "id": item.get("id"),
        "mission_patch_id": item.get("mission_patch_id"),
        "action_type": item.get("action_type"),
        "target_asset_id": item.get("target_asset_id"),
        "status": item.get("status"),
        "input": _compact_action(item.get("input")),
        "result": item.get("result"),
    }


def _status_counts(items: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = str(_mapping(item).get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _thermal_context(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "thermal": state.get("thermal", {}),
        "nodes": state.get("nodes", []),
        "power": state.get("power", {}),
        "training": state.get("training", {}),
    }


def _agent_context(agent_name: str, state: dict[str, Any]) -> dict[str, Any]:
    common = {
        "satellite": state.get("satellite", {}),
        "training": state.get("training", {}),
        "nodes": state.get("nodes", []),
    }
    if agent_name == "workload_agent":
        return {**common, "workload_nodes": state.get("nodes", [])}
    if agent_name == "thermal_physical_agent":
        return {**common, "thermal": state.get("thermal", {}), "power": state.get("power", {})}
    if agent_name == "power_orbit_agent":
        return {**common, "power": state.get("power", {}), "downlink": state.get("downlink", {})}
    if agent_name == "radiation_integrity_agent":
        return {**common, "radiation": state.get("radiation", {})}
    if agent_name == "checkpoint_downlink_agent":
        return {**common, "downlink": state.get("downlink", {})}
    if agent_name == "vibration_health_agent":
        return {**common, "thermal": state.get("thermal", {})}
    return state


def _normalize_agent_analysis(parsed: dict[str, Any], allowed_actions: list[str]) -> dict[str, Any]:
    allowed = set(allowed_actions)
    return {
        "summary": _bounded_text(_as_string(parsed.get("summary")), MAX_AGENT_ANALYSIS_CHARS),
        "confidence": _as_float(parsed.get("confidence")),
        "evidence": _as_string_list(parsed.get("evidence"))[:6],
        "risk": _bounded_text(_as_string(parsed.get("risk")), MAX_AGENT_ANALYSIS_CHARS),
        "recommended_actions": [
            action for action in _as_string_list(parsed.get("recommended_actions")) if action in allowed
        ],
        "model": settings.crusoe_model,
        "provider": "crusoe",
    }


def _normalize_thermal_analysis(parsed: dict[str, Any]) -> dict[str, Any]:
    allowed_actions = AGENT_ACTION_ALLOWLISTS["thermal_physical_agent"]
    audit_verdict = _audit_verdict(parsed)
    fail_only_questions = _as_string_list(parsed.get("questions")) if audit_verdict == "fail" else []
    fail_only_actions = _as_string_list(parsed.get("recommended_actions")) if audit_verdict == "fail" else []
    return {
        "audit_verdict": audit_verdict,
        "summary": _as_string(parsed.get("summary")),
        "confidence": _as_float(parsed.get("confidence")),
        "affected_assets": _as_string_list(parsed.get("affected_assets")),
        "evidence": _as_string_list(parsed.get("evidence")),
        "risk": _as_string(parsed.get("risk")),
        "recommended_actions": [
            action for action in fail_only_actions if action in allowed_actions
        ],
        "questions": fail_only_questions,
        "needs_human_review": audit_verdict == "fail",
        "model": settings.crusoe_multimodal_model or NEMOTRON_OMNI_MODEL,
        "provider": "crusoe",
    }


def _audit_verdict(parsed: dict[str, Any]) -> str:
    verdict = parsed.get("audit_verdict") or parsed.get("verdict")
    if isinstance(verdict, str):
        normalized = verdict.strip().lower()
        if normalized in {"pass", "warn", "fail"}:
            return normalized
    confidence = _as_float(parsed.get("confidence"))
    if confidence is not None and confidence < 0.55:
        return "fail"
    return "pass"


def _as_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _as_float(value: Any) -> float | None:
    if isinstance(value, int | float):
        return max(0.0, min(1.0, float(value)))
    return None


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
