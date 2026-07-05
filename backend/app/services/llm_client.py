"""Optional Crusoe/Nemotron integrations for agent evidence interpretation."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import settings


NEMOTRON_OMNI_MODEL = "nvidia/Nemotron-3-Nano-Omni-Reasoning-30B-A3B"


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
        messages=[
            {
                "role": "system",
                "content": (
                    "You rewrite mission patch summaries for orbital data-center operators. "
                    "Do not add new facts, actions, or confidence claims."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Rewrite this summary in one concise operational paragraph.\n\n"
                    f"Summary: {summary}\n\nContext keys: {', '.join(sorted(context.keys()))}"
                ),
            },
        ],
        max_tokens=256,
        temperature=0.2,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    content = _message_content(response)
    return content.strip() if content else summary


async def analyze_thermal_ir_image(
    image_data_url: str,
    *,
    state: dict[str, Any],
    finding: dict[str, Any],
) -> dict[str, Any] | None:
    """Ask Nemotron Omni to interpret a thermal IR frame for the thermal agent.

    Deterministic thresholds still decide the finding and executable actions.
    The model is used as a perception/evidence layer for image-specific detail:
    visible hotspot pattern, likely affected asset, useful questions, and
    operator-readable explanation.
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
                    "Return only a JSON object with keys: summary, confidence, affected_assets, evidence, "
                    "risk, recommended_actions, questions, needs_human_review. "
                    "Keep recommendations within this allowlist: mark_node_suspect, set_gpu_power_limit, "
                    "run_health_check, snapshot_evidence. Do not invent assets outside the telemetry.\n\n"
                    f"Telemetry JSON: {json.dumps(_thermal_context(state), sort_keys=True)}\n"
                    f"Deterministic finding JSON: {json.dumps(finding, sort_keys=True)}"
                ),
            },
        ],
    }
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
    parsed = _parse_json_object(_message_content(response))
    if not parsed:
        return None
    return _normalize_thermal_analysis(parsed)


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


def _message_content(response: dict[str, Any] | None) -> str:
    if not response:
        return ""
    choices = response.get("choices") or []
    if not choices:
        return ""
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""


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


def _thermal_context(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "thermal": state.get("thermal", {}),
        "nodes": state.get("nodes", []),
        "power": state.get("power", {}),
        "training": state.get("training", {}),
    }


def _normalize_thermal_analysis(parsed: dict[str, Any]) -> dict[str, Any]:
    allowed_actions = {"mark_node_suspect", "set_gpu_power_limit", "run_health_check", "snapshot_evidence"}
    return {
        "summary": _as_string(parsed.get("summary")),
        "confidence": _as_float(parsed.get("confidence")),
        "affected_assets": _as_string_list(parsed.get("affected_assets")),
        "evidence": _as_string_list(parsed.get("evidence")),
        "risk": _as_string(parsed.get("risk")),
        "recommended_actions": [
            action for action in _as_string_list(parsed.get("recommended_actions")) if action in allowed_actions
        ],
        "questions": _as_string_list(parsed.get("questions")),
        "needs_human_review": bool(parsed.get("needs_human_review")),
        "model": settings.crusoe_multimodal_model or NEMOTRON_OMNI_MODEL,
        "provider": "crusoe",
    }


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
