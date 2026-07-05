from __future__ import annotations

from types import SimpleNamespace

from app.services.agent_prompts import (
    AGENT_ACTION_ALLOWLISTS,
    AGENT_PROMPTS,
    COMMANDER_ORCHESTRATION_SCHEMA,
    agent_analysis_system_prompt,
    commander_summary_messages,
)
from app.services import llm_client

DOMAIN_AGENTS = [
    "workload_agent",
    "thermal_physical_agent",
    "power_orbit_agent",
    "radiation_integrity_agent",
    "checkpoint_downlink_agent",
    "vibration_health_agent",
]

LEGACY_ALLOWLISTS = {
    "workload_agent": {"snapshot_evidence", "run_health_check", "pause_job", "rollback_training"},
    "thermal_physical_agent": {"mark_node_suspect", "set_gpu_power_limit", "run_health_check", "snapshot_evidence"},
    "power_orbit_agent": {"increase_checkpoint_frequency", "set_gpu_power_limit", "transfer_priority"},
    "radiation_integrity_agent": {"mark_checkpoint_suspect", "cordon_node", "run_health_check", "rollback_training"},
    "checkpoint_downlink_agent": {"transfer_priority", "snapshot_evidence"},
    "vibration_health_agent": {"snapshot_evidence", "run_health_check", "mark_node_suspect"},
}


def test_registry_covers_every_domain_agent() -> None:
    assert set(AGENT_PROMPTS) == set(DOMAIN_AGENTS)


def test_allowlists_match_legacy_values() -> None:
    assert AGENT_ACTION_ALLOWLISTS == LEGACY_ALLOWLISTS
    assert llm_client.AGENT_ACTION_ALLOWLISTS == LEGACY_ALLOWLISTS


def test_each_agent_prompt_is_specific() -> None:
    prompts = {name: agent_analysis_system_prompt(name) for name in DOMAIN_AGENTS}
    assert len(set(prompts.values())) == len(DOMAIN_AGENTS)
    for name, prompt in prompts.items():
        spec = AGENT_PROMPTS[name]
        assert name in prompt
        for action in spec.allowed_actions:
            assert action in prompt
        assert "Hypotheses" in prompt
        assert "Evidence quality" in prompt
        assert "Escalate" in prompt
        assert "never" in prompt.lower()


def test_prompts_state_real_thresholds() -> None:
    assert "88" in agent_analysis_system_prompt("thermal_physical_agent")
    assert "900" in agent_analysis_system_prompt("radiation_integrity_agent")
    assert "45%" in agent_analysis_system_prompt("power_orbit_agent")
    assert "15 minutes" in agent_analysis_system_prompt("power_orbit_agent")
    assert "180 GB" in agent_analysis_system_prompt("checkpoint_downlink_agent")
    assert "0.75" in agent_analysis_system_prompt("vibration_health_agent")
    assert "5%" in agent_analysis_system_prompt("workload_agent")


def test_unknown_agent_gets_generic_fallback() -> None:
    prompt = agent_analysis_system_prompt("mystery_agent")
    assert "mystery_agent" in prompt
    assert "summary, confidence, evidence, risk, recommended_actions" in prompt


def test_commander_schema_pins_human_approval() -> None:
    assert COMMANDER_ORCHESTRATION_SCHEMA["properties"]["approval_required"] == {"const": True}
    assert set(COMMANDER_ORCHESTRATION_SCHEMA["properties"]["dispatch_agents"]["items"]["enum"]) == set(DOMAIN_AGENTS)


def test_commander_summary_messages_render_findings_from_orm_like_objects() -> None:
    finding = SimpleNamespace(
        agent_name="radiation_integrity_agent",
        severity="RED",
        confidence=0.91,
        finding="ECC burst above threshold.",
        risk="Checkpoint may be corrupted.",
    )
    world_state = {
        "power": {"battery_percent": 41},
        "satellite": {"time_to_eclipse_min": 11},
        "training": {"latest_checkpoint_status": "suspect"},
    }
    messages = commander_summary_messages("Deterministic summary.", {"findings": [finding], "world_state": world_state})

    assert messages[0]["role"] == "system"
    assert "Commander Agent" in messages[0]["content"]
    user_content = messages[1]["content"]
    assert "Deterministic summary." in user_content
    assert "ECC burst above threshold." in user_content
    assert "radiation_integrity_agent" in user_content
    assert "battery_percent=41" in user_content
    assert "object at 0x" not in user_content


def test_commander_summary_messages_handle_dict_findings_and_empty_context() -> None:
    messages = commander_summary_messages(
        "Summary only.",
        {"findings": [{"agent_name": "workload_agent", "severity": "ORANGE", "finding": "Rank lag detected."}]},
    )
    assert "Rank lag detected." in messages[1]["content"]

    empty = commander_summary_messages("Summary only.", {})
    assert "none provided" in empty[1]["content"]
