from __future__ import annotations

import asyncio
import json
import os

from langchain_core.messages import HumanMessage, SystemMessage

from .crusoe_client import get_llm, mock_mode
from .mock_crusoe import chat_fallback, local_recommendation, local_why
from .models import (
    AgentRecommendation,
    CandidateAction,
    ClusterState,
    DomainRisk,
    RiskForecast,
    SituationalFinding,
    WhyResponse,
)
from .prompts import ADVISORY_SYSTEM_PROMPT, WHY_SYSTEM_PROMPT


async def generate_advisory(
    cluster: ClusterState,
    domain_risks: list[DomainRisk],
    forecast: RiskForecast,
    findings: list[SituationalFinding],
    candidates: list[CandidateAction],
) -> AgentRecommendation:
    if mock_mode():
        return local_recommendation(cluster, domain_risks, forecast, findings, candidates, source="mock")

    payload = _advisory_payload(cluster, domain_risks, forecast, findings, candidates)
    advisory_model = os.getenv("ASTROOPS_ADVISORY_MODEL", "nemotron_omni").strip() or "nemotron_omni"
    try:
        llm = get_llm(advisory_model, structured=True)
        structured = llm.with_structured_output(AgentRecommendation)
        result: AgentRecommendation = await asyncio.to_thread(
            structured.invoke,
            [
                SystemMessage(content=ADVISORY_SYSTEM_PROMPT),
                HumanMessage(content=json.dumps(payload, indent=2)),
            ],
        )
        result.source = "crusoe"
        return result
    except Exception as exc:
        message = str(exc)
        if "412" in message:
            await asyncio.sleep(1.2)
            try:
                llm = get_llm(advisory_model, structured=True)
                structured = llm.with_structured_output(AgentRecommendation)
                result = await asyncio.to_thread(
                    structured.invoke,
                    [
                        SystemMessage(content=ADVISORY_SYSTEM_PROMPT),
                        HumanMessage(content=json.dumps(payload, indent=2)),
                    ],
                )
                result.source = "crusoe"
                return result
            except Exception:
                pass
        return local_recommendation(cluster, domain_risks, forecast, findings, candidates, source="fallback")


async def explain_why(
    recommendation: AgentRecommendation,
    candidates: list[CandidateAction],
    cluster: ClusterState,
    forecast: RiskForecast,
) -> WhyResponse:
    if mock_mode() or recommendation.source != "crusoe":
        return local_why(recommendation.advisory_id, recommendation, candidates, source=recommendation.source)
    try:
        fast_model = os.getenv("ASTROOPS_FAST_MODEL", "nemotron_omni").strip() or "nemotron_omni"
        llm = get_llm(fast_model, disable_thinking=True)
        payload = {
            "recommendation": recommendation.model_dump(),
            "candidate_actions": [c.model_dump() for c in candidates],
            "forecast": forecast.model_dump(),
            "policy_notes": cluster.policy_notes,
        }
        text = await asyncio.to_thread(
            llm.invoke,
            [SystemMessage(content=WHY_SYSTEM_PROMPT), HumanMessage(content=json.dumps(payload, indent=2))],
        )
        content = getattr(text, "content", "") or ""
        fallback = local_why(recommendation.advisory_id, recommendation, candidates, source="crusoe")
        fallback.why_this_action = content[:900] or fallback.why_this_action
        fallback.source = "crusoe"
        return fallback
    except Exception:
        return local_why(recommendation.advisory_id, recommendation, candidates, source="fallback")


async def answer_chat(
    message: str,
    recommendation: AgentRecommendation | None,
    cluster: ClusterState,
    forecast: RiskForecast,
    domain_risks: list[DomainRisk],
) -> str:
    if mock_mode():
        return chat_fallback(message, recommendation, forecast)
    try:
        fast_model = os.getenv("ASTROOPS_FAST_MODEL", "nemotron_omni").strip() or "nemotron_omni"
        llm = get_llm(fast_model, disable_thinking=True)
        payload = {
            "operator_question": message,
            "current_recommendation": recommendation.model_dump() if recommendation else None,
            "forecast": forecast.model_dump(),
            "top_risks": [risk.model_dump() for risk in sorted(domain_risks, key=lambda item: item.score, reverse=True)[:5]],
            "policy_notes": cluster.policy_notes,
        }
        response = await asyncio.to_thread(
            llm.invoke,
            [
                SystemMessage(content="You are AstroOps Live. Answer concisely using only the provided operational state."),
                HumanMessage(content=json.dumps(payload, indent=2)),
            ],
        )
        return getattr(response, "content", "") or chat_fallback(message, recommendation, forecast)
    except Exception:
        return chat_fallback(message, recommendation, forecast)


def _advisory_payload(
    cluster: ClusterState,
    domain_risks: list[DomainRisk],
    forecast: RiskForecast,
    findings: list[SituationalFinding],
    candidates: list[CandidateAction],
) -> dict:
    return {
        "cluster_summary": {
            "cluster_id": cluster.cluster_id,
            "region": cluster.region,
            "scenario": cluster.scenario_id,
            "tick": cluster.tick,
            "time_min": cluster.simulated_time_min,
        },
        "top_findings": [finding.model_dump() for finding in findings[:5]],
        "domain_risks": [risk.model_dump() for risk in domain_risks],
        "forecast": forecast.model_dump(),
        "candidate_actions": [candidate.model_dump() for candidate in candidates],
        "jobs": [job.model_dump() for job in cluster.jobs],
        "racks": [
            {
                "rack_id": rack.rack_id,
                "risk": rack.overall_risk_score,
                "level": rack.risk_level,
                "inlet_c": rack.rack_inlet_temp_c,
                "thermal_slope": rack.thermal_slope_c_per_min,
                "pdu_load": rack.pdu_load_pct,
                "available_gpu_slots": rack.available_gpu_slots,
                "safe_destination": rack.safe_destination,
            }
            for rack in cluster.racks
        ],
        "override_history": [record.model_dump() for record in cluster.override_history[-5:]],
        "accepted_actions": [record.model_dump() for record in cluster.accepted_actions[-5:]],
        "policy_notes": cluster.policy_notes,
    }
