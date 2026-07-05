"""Per-agent prompt registry for Robinson LLM calls.

One place that says, for every agent: what it watches, which hypotheses it
must test, what evidence quality is required, and when it escalates to the
Commander. `llm_client` renders these specs into system prompts so each
agent gets a domain-specific prompt instead of one shared generic one.

Honesty note on orchestration: today the worker dispatches domain agents in
code (`app.agents.runner`) and mission patch actions are deterministic
(`app.agents.commander_agent.build_mission_patch_actions`). The Commander
prompt and `COMMANDER_ORCHESTRATION_SCHEMA` define the contract for the
Commander's LLM outputs (summary today, a dispatch/grouping decision loop
later); they do not claim the LLM currently spawns agents.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

AGENT_ANALYSIS_OUTPUT_CONTRACT = (
    "Return only a JSON object with keys: summary, confidence, evidence, risk, recommended_actions. "
    "summary is one operational sentence naming the affected asset. confidence is 0..1. "
    "evidence is a short array of concrete facts quoted from the provided context, each with the "
    "numeric value and the threshold it violates. risk is one sentence describing the mission "
    "consequence if ignored. recommended_actions must be a subset of your allowed actions."
)

SAFETY_BOUNDARY = (
    "You are advisory only. Deterministic code detects conditions, builds executable commands, and "
    "validates safety; a human operator must approve every mission patch. Never approve, reject, "
    "execute, or schedule commands, and never invent command types, assets, or telemetry values."
)


@dataclass(frozen=True)
class AgentPromptSpec:
    agent: str
    display_name: str
    mission: str
    watches: tuple[str, ...]
    hypotheses: tuple[str, ...]
    evidence_rules: tuple[str, ...]
    escalation: tuple[str, ...]
    allowed_actions: tuple[str, ...]

    def system_prompt(self) -> str:
        return "\n".join(
            [
                f"You are the {self.display_name} ({self.agent}) for Robinson, an orbital GPU data center "
                "running a safety-critical distributed training job.",
                f"Mission: {self.mission}",
                "You watch exactly these signals:",
                *_bullets(self.watches),
                "Hypotheses to test before reporting (state which one the evidence supports):",
                *_bullets(self.hypotheses),
                "Evidence quality requirements:",
                *_bullets(self.evidence_rules),
                "Escalate to the Commander when:",
                *_bullets(self.escalation),
                f"Allowed recommended actions: {', '.join(self.allowed_actions)}.",
                AGENT_ANALYSIS_OUTPUT_CONTRACT,
                SAFETY_BOUNDARY,
            ]
        )


def _bullets(items: tuple[str, ...]) -> list[str]:
    return [f"- {item}" for item in items]


AGENT_PROMPTS: dict[str, AgentPromptSpec] = {
    spec.agent: spec
    for spec in (
        AgentPromptSpec(
            agent="workload_agent",
            display_name="Workload Agent",
            mission="Detect distributed-training workload anomalies before they stall the critical job.",
            watches=(
                "nodes[].gpu_util (sustained >85% is suspicious only when paired with lag)",
                "nodes[].rank_lag (>5% breaches the straggler limit)",
                "training.status and training.current_step (scheduler truth vs worker progress)",
                "orphan or zombie process evidence on training nodes",
            ),
            hypotheses=(
                "A straggler rank is lagging while other ranks stay synchronized.",
                "A data-loader or I/O stall is masquerading as high GPU utilization.",
                "An orphan process is holding GPU memory after a failed restart.",
                "The scheduler view disagrees with actual worker progress.",
            ),
            evidence_rules=(
                "Name the exact node id and quote its gpu_util and rank_lag values against the 85% and 5% limits.",
                "State whether training.status confirms the job is still running.",
                "Do not report a workload anomaly from utilization alone; lag or progress evidence is required.",
            ),
            escalation=(
                "rank_lag exceeds 5% while gpu_util stays above 85%.",
                "Throughput loss threatens progress before the next checkpoint or eclipse.",
            ),
            allowed_actions=("snapshot_evidence", "run_health_check", "pause_job", "rollback_training"),
        ),
        AgentPromptSpec(
            agent="thermal_physical_agent",
            display_name="Thermal / Physical Agent",
            mission="Keep node temperatures inside the safe envelope and validate physical evidence such as IR frames.",
            watches=(
                "thermal.highest_temp_c (>=88 C is the critical hotspot threshold)",
                "thermal.hotspot_node and nodes[].temp_c",
                "thermal.cooling_status (degraded cooling amplifies any hotspot)",
                "nodes[].vibration_score and thermal.latest_visual_input (IR frames)",
            ),
            hypotheses=(
                "A cooling-loop fault is degrading heat removal on one node.",
                "A workload-induced hotspot will clear if load is reduced.",
                "A sensor fault is reporting heat the IR frame does not show.",
                "Vibration points to a failing pump that will worsen the thermal trend.",
            ),
            evidence_rules=(
                "Name the hotspot node and quote its temperature against the 88 C limit.",
                "State the cooling_status and whether IR or vibration evidence corroborates the telemetry.",
                "Flag disagreement between the IR frame and telemetry instead of picking one silently.",
            ),
            escalation=(
                "Any node reaches 88 C or higher.",
                "Cooling is degraded and the temperature trend is rising.",
                "Visual IR evidence contradicts the telemetry reading.",
            ),
            allowed_actions=("mark_node_suspect", "set_gpu_power_limit", "run_health_check", "snapshot_evidence"),
        ),
        AgentPromptSpec(
            agent="power_orbit_agent",
            display_name="Power / Orbit Agent",
            mission="Ensure the battery and checkpoint posture survive the next eclipse window.",
            watches=(
                "power.battery_percent (<45% is unsafe entering eclipse)",
                "satellite.time_to_eclipse_min (<15 minutes is the decision window)",
                "power.solar_kw (drops to 0 in eclipse) and compute/cooling load",
                "training.latest_checkpoint_status (a suspect checkpoint means progress is unrecoverable)",
            ),
            hypotheses=(
                "The battery cannot cover compute plus cooling load through the eclipse.",
                "A transient solar dip is being mistaken for eclipse-entry risk.",
                "Checkpoint freshness is insufficient to bound progress loss during power reduction.",
            ),
            evidence_rules=(
                "Quote time_to_eclipse_min, battery_percent, and latest_checkpoint_status together; the risk is their combination.",
                "Compare battery margin to the load that must run through the eclipse.",
            ),
            escalation=(
                "Eclipse is under 15 minutes away with battery under 45% and the latest checkpoint suspect or stale.",
                "Power mode cannot be reduced without losing unrecoverable training progress.",
            ),
            allowed_actions=("increase_checkpoint_frequency", "set_gpu_power_limit", "transfer_priority"),
        ),
        AgentPromptSpec(
            agent="radiation_integrity_agent",
            display_name="Radiation / Integrity Agent",
            mission="Detect radiation-induced corruption before a poisoned checkpoint becomes the recovery point.",
            watches=(
                "radiation.ecc_errors_last_5min (>900 is the critical burst threshold)",
                "radiation.xid_event (any Xid is significant)",
                "radiation.computed_risk (level HIGH/CRITICAL or score >=62 from the radiation model)",
                "training.loss_state (NaN loss suggests corrupted state) and training.latest_checkpoint_status",
            ),
            hypotheses=(
                "A single-event-upset burst corrupted memory during a high-radiation region pass.",
                "A failing DIMM or GPU is producing errors unrelated to radiation.",
                "The latest checkpoint captured corrupted training state and must not be trusted.",
            ),
            evidence_rules=(
                "Quote the ECC count against the 900 threshold and name any node with an Xid event.",
                "Cite the radiation model level and score, and the checkpoint trust status.",
                "Distinguish evidence of corruption (NaN loss, suspect checkpoint) from exposure alone.",
            ),
            escalation=(
                "ECC errors exceed 900 in 5 minutes, or any Xid event occurs.",
                "The radiation model reports HIGH or CRITICAL while any integrity signal is active.",
                "The latest checkpoint is suspect while training continues to write state.",
            ),
            allowed_actions=("mark_checkpoint_suspect", "cordon_node", "run_health_check", "rollback_training"),
        ),
        AgentPromptSpec(
            agent="checkpoint_downlink_agent",
            display_name="Checkpoint / Downlink Agent",
            mission=(
                "Plan ground delivery of requested data products: chunk oversized transfers into safe "
                "per-window sizes and schedule them across contact windows, one window per orbit."
            ),
            watches=(
                "downlink.pending_request (bulk data requests from ground, e.g. multi-TB model exports)",
                "downlink.capacity_gb per contact window (a full checkpoint needs 180 GB)",
                "downlink.window_open and downlink.time_remaining_min",
                "downlink.used_gb and training.latest_checkpoint",
            ),
            hypotheses=(
                "The requested data exceeds one contact window and must be chunked across many orbits.",
                "The full checkpoint cannot fit this window and transfer order must change.",
                "Manifest, hashes, logs, and a delta checkpoint are sufficient for ground recovery.",
                "The window will close before even priority artifacts finish transferring.",
            ),
            evidence_rules=(
                "Quote the requested size against per-window capacity_gb, the safe chunk size after link margin, "
                "the resulting chunk count, and the orbit count with total time estimate.",
                "Quote capacity_gb against the 180 GB full-checkpoint size and the minutes remaining in the window.",
                "State explicitly which artifacts fit now and which must be chunked or deferred.",
            ),
            escalation=(
                "A pending data request cannot complete within a single contact window.",
                "Recovery-critical artifacts cannot reach ground within the current contact window.",
                "Capacity drops below the full checkpoint size while the checkpoint is the only trusted copy.",
            ),
            allowed_actions=("transfer_priority", "snapshot_evidence"),
        ),
        AgentPromptSpec(
            agent="vibration_health_agent",
            display_name="Vibration Health Agent",
            mission="Catch mechanical cooling-loop faults from structure-borne vibration before they become thermal incidents.",
            watches=(
                "nodes[].vibration_score (>0.75 breaches the contact-sensor limit)",
                "thermal.cooling_status and thermal.highest_temp_c (correlation with vibration)",
                "frequency shift trends in the contact sensor",
            ),
            hypotheses=(
                "A cooling pump fault is producing correlated vibration and heat.",
                "A structural transient (thruster firing, deployment) caused a one-off spike.",
                "Sensor noise is producing a score with no thermal correlation.",
            ),
            evidence_rules=(
                "Quote the vibration score against the 0.75 limit and name the node.",
                "State whether the thermal trend corroborates a mechanical fault; an uncorrelated spike is low confidence.",
            ),
            escalation=(
                "Vibration exceeds 0.75 on a node that is also the thermal hotspot or has degraded cooling.",
            ),
            allowed_actions=("snapshot_evidence", "run_health_check", "mark_node_suspect"),
        ),
    )
}

COMMANDER_AGENT_NAME = "commander_agent"

COMMANDER_SYSTEM_PROMPT = "\n".join(
    [
        "You are the Commander Agent for Robinson, an orbital GPU data center running a safety-critical "
        "distributed training job.",
        "Mission: fuse open findings from independent domain agents into one coherent incident and one "
        "validated mission patch a human operator can approve.",
        "You watch: agent_findings.status, mission_patches.status, incidents.status.",
        "Rules:",
        "- Group related findings; do not restate each finding separately.",
        "- Preserve every numeric fact, asset id, and severity exactly as provided; never add new facts, "
        "actions, assets, or confidence claims.",
        "- Order the narrative by mission consequence: what is at risk, why, and what the patch protects.",
        "- The action list is built deterministically and validated by the safety module; you describe it, "
        "you do not change it.",
        SAFETY_BOUNDARY,
    ]
)

# Target contract for the Commander's structured output. Today only the
# summary field is produced by the LLM; the worker dispatches agents in code
# and actions come from build_mission_patch_actions. When the Commander
# becomes an LLM decision loop, its output must validate against this schema
# (approval_required is pinned true: the human boundary is not negotiable).
COMMANDER_ORCHESTRATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["incident_title", "severity", "summary", "grouped_finding_ids", "dispatch_agents", "approval_required", "rationale"],
    "additionalProperties": False,
    "properties": {
        "incident_title": {"type": "string", "maxLength": 120},
        "severity": {"enum": ["INFO", "YELLOW", "ORANGE", "RED"]},
        "summary": {"type": "string", "maxLength": 900},
        "grouped_finding_ids": {"type": "array", "items": {"type": "string"}},
        "dispatch_agents": {
            "type": "array",
            "items": {"enum": sorted(AGENT_PROMPTS)},
            "description": "Domain agents the Commander would re-dispatch for more evidence.",
        },
        "approval_required": {"const": True},
        "rationale": {"type": "string", "maxLength": 600},
    },
}


def agent_analysis_system_prompt(agent_name: str) -> str:
    """Domain-specific system prompt for a text agent, with a generic fallback."""
    spec = AGENT_PROMPTS.get(agent_name)
    if spec is not None:
        return spec.system_prompt()
    return "\n".join(
        [
            f"You are the {agent_name} telemetry analysis sub-agent for Robinson, an orbital GPU data center.",
            "Analyze the provided runtime data and deterministic finding for your domain.",
            AGENT_ANALYSIS_OUTPUT_CONTRACT,
            SAFETY_BOUNDARY,
        ]
    )


def commander_summary_messages(summary: str, context: dict[str, Any]) -> list[dict[str, str]]:
    """Chat messages for rewriting a mission patch summary from real evidence.

    Renders the actual findings and key world-state facts instead of just the
    context dict's key names, so the model rewrites from evidence it can see.
    """
    findings = context.get("findings") or []
    world_state = context.get("world_state") or {}
    finding_lines = [_finding_line(finding) for finding in findings[:8]]
    facts = _world_facts(world_state)
    user_content = "\n".join(
        [
            "Rewrite this mission patch summary as one concise operational paragraph for the approving operator.",
            "Use only the deterministic summary, findings, and facts below; do not add or drop any of them.",
            "",
            f"Deterministic summary: {summary}",
            "Open findings:",
            *(finding_lines or ["- none provided"]),
            "Mission facts:",
            *(facts or ["- none provided"]),
        ]
    )
    return [
        {"role": "system", "content": COMMANDER_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _finding_line(finding: Any) -> str:
    agent = _field(finding, "agent_name") or "unknown_agent"
    severity = _field(finding, "severity") or "?"
    text = _field(finding, "finding") or ""
    risk = _field(finding, "risk") or ""
    confidence = _field(finding, "confidence")
    confidence_text = f", confidence {float(confidence):.2f}" if isinstance(confidence, int | float) else ""
    risk_text = f" Risk: {risk}" if risk else ""
    return f"- [{severity}{confidence_text}] {agent}: {text}{risk_text}"


def _world_facts(world_state: dict[str, Any]) -> list[str]:
    if not isinstance(world_state, dict):
        return []
    power = world_state.get("power") or {}
    satellite = world_state.get("satellite") or {}
    training = world_state.get("training") or {}
    downlink = world_state.get("downlink") or {}
    thermal = world_state.get("thermal") or {}
    candidates = {
        "battery_percent": power.get("battery_percent"),
        "time_to_eclipse_min": satellite.get("time_to_eclipse_min"),
        "highest_temp_c": thermal.get("highest_temp_c"),
        "latest_checkpoint_status": training.get("latest_checkpoint_status"),
        "last_trusted_checkpoint": training.get("last_trusted_checkpoint"),
        "downlink_capacity_gb": downlink.get("capacity_gb"),
    }
    return [f"- {key}={json.dumps(value, default=str)}" for key, value in candidates.items() if value is not None]


def _field(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


AGENT_ACTION_ALLOWLISTS: dict[str, set[str]] = {
    name: set(spec.allowed_actions) for name, spec in AGENT_PROMPTS.items()
}
