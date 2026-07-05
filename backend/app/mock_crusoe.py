from __future__ import annotations

from uuid import uuid4

from .models import (
    AgentRecommendation,
    CandidateAction,
    ClusterState,
    DomainRisk,
    RiskForecast,
    SituationalFinding,
    WhyResponse,
    iso_now,
)


def local_recommendation(
    cluster: ClusterState,
    domain_risks: list[DomainRisk],
    forecast: RiskForecast,
    findings: list[SituationalFinding],
    candidates: list[CandidateAction],
    source: str = "mock",
) -> AgentRecommendation:
    valid = [action for action in candidates if not action.blocked_by_operator_policy]
    selected = max(valid or candidates, key=lambda action: action.estimated_risk_reduction)
    rejected = [
        f"{action.title}: {action.why_not_valid or action.downside}"
        for action in candidates
        if action.action_id != selected.action_id
    ][:4]
    top_domains = sorted(domain_risks, key=lambda item: item.score, reverse=True)[:4]
    level = "critical" if forecast.risk_now >= 75 else "high" if forecast.risk_now >= 55 else "watch"
    eta = _first_eta(forecast)
    predicted = _predicted_failure(cluster.scenario_id, top_domains)
    steps = _steps_for_action(selected)
    return AgentRecommendation(
        advisory_id=str(uuid4())[:8],
        timestamp=iso_now(),
        risk_level=level,
        headline=_headline(cluster.scenario_id, forecast),
        situation_summary=_summary(cluster, top_domains, forecast),
        predicted_failure_mode=predicted,
        affected_entities=_affected_entities(cluster.scenario_id),
        eta_minutes=eta,
        overall_risk_score_before=forecast.risk_now,
        overall_risk_score_after_estimate=max(0, forecast.risk_now - selected.estimated_risk_reduction),
        recommended_action_id=selected.action_id,
        recommended_action_title=selected.title,
        recommended_action_steps=steps,
        evidence_bullets=_evidence(findings, top_domains),
        candidate_actions_considered=[action.title for action in candidates],
        rejected_actions=rejected,
        expected_impact=(
            f"Estimated risk falls from {forecast.risk_now:.0f}/100 to "
            f"{max(0, forecast.risk_now - selected.estimated_risk_reduction):.0f}/100 while preserving higher-priority workloads."
        ),
        if_no_action=_if_no_action(cluster.scenario_id, eta),
        confidence=0.86 if source == "mock" else 0.78,
        operator_questions=[
            "Confirm destination rack capacity?",
            "Any maintenance note that blocks the selected action?",
            "Proceed now or wait for checkpoint window?",
        ],
        source=source,  # type: ignore[arg-type]
    )


def local_why(
    advisory_id: str,
    recommendation: AgentRecommendation,
    candidates: list[CandidateAction],
    source: str = "mock",
) -> WhyResponse:
    selected = next((action for action in candidates if action.action_id == recommendation.recommended_action_id), None)
    return WhyResponse(
        advisory_id=advisory_id,
        why_this_action=selected.why_valid if selected else recommendation.expected_impact,
        why_not_alternatives=[
            action.why_not_valid or action.downside
            for action in candidates
            if action.action_id != recommendation.recommended_action_id
        ][:3],
        if_no_action=recommendation.if_no_action,
        signal_changed_most=recommendation.evidence_bullets[0] if recommendation.evidence_bullets else "Composite risk is worsening.",
        source=source,  # type: ignore[arg-type]
    )


def chat_fallback(message: str, recommendation: AgentRecommendation | None, forecast: RiskForecast) -> str:
    if recommendation:
        return (
            f"Current advisory: {recommendation.recommended_action_title}. "
            f"Risk is {forecast.risk_now:.0f}/100 now and forecast to {forecast.risk_plus_10:.0f}/100 in 10 minutes. "
            f"The main reason is: {recommendation.evidence_bullets[0] if recommendation.evidence_bullets else 'compound risk is rising'}."
        )
    return (
        f"Risk is {forecast.risk_now:.0f}/100 now. No active advisory is selected yet. "
        "Generate a recommendation when the situation reaches high or critical risk."
    )


def _first_eta(forecast: RiskForecast) -> float | None:
    values = [
        forecast.eta_to_throttle_min,
        forecast.eta_to_sla_breach_min,
        forecast.eta_to_network_congestion_min,
        forecast.eta_to_gpu_failure_risk_min,
    ]
    numeric = [value for value in values if value is not None]
    return min(numeric) if numeric else None


def _headline(scenario_id: str, forecast: RiskForecast) -> str:
    if scenario_id in {"cascade", "override_learning"}:
        return f"R-3 compound risk likely to affect service in {(_first_eta(forecast) or 9):.0f} minutes"
    if scenario_id == "gpu_health":
        return "R-5/N-2/GPU-3 should be drained before it fails a workload"
    return "Inference SLA pressure requires capacity action before breach"


def _summary(cluster: ClusterState, top_domains: list[DomainRisk], forecast: RiskForecast) -> str:
    domains = ", ".join(f"{risk.domain} {risk.score:.0f}" for risk in top_domains[:3])
    return (
        f"{cluster.cluster_id} is at {forecast.risk_now:.0f}/100 overall risk. "
        f"The dominant domains are {domains}; the forecast worsens to {forecast.risk_plus_10:.0f}/100 in ten minutes."
    )


def _predicted_failure(scenario_id: str, top_domains: list[DomainRisk]) -> str:
    if scenario_id in {"cascade", "override_learning"}:
        return "Cascading incident: thermal throttling plus queue/SLA and network degradation"
    if scenario_id == "gpu_health":
        return "GPU health anomaly leading to job failure or forced reschedule"
    return "Inference SLA breach caused by queue saturation and insufficient serving replicas"


def _affected_entities(scenario_id: str) -> list[str]:
    if scenario_id in {"cascade", "override_learning"}:
        return ["R-3", "R-7", "J-184", "J-104", "R-3:R-4"]
    if scenario_id == "gpu_health":
        return ["R-5/N-2/GPU-3", "J-184", "R-7"]
    return ["inference-service", "J-331", "R-8"]


def _steps_for_action(action: CandidateAction) -> list[str]:
    if action.action_id == "act-cascade-bundle":
        return [
            "Wait until the high-priority training checkpoint is safe.",
            "Migrate low-priority J-184 from R-3 to R-7.",
            "Cordon R-3 for new placements.",
            "Apply a temporary 8% power cap on R-3.",
        ]
    if action.action_id == "act-quarantine-gpu":
        return [
            "Let the active checkpoint finish.",
            "Drain R-5/N-2/GPU-3.",
            "Reschedule the workload on R-7.",
            "Mark the GPU quarantined for hardware review.",
        ]
    if action.action_id == "act-scale-inference":
        return [
            "Pause low-priority J-331.",
            "Use the freed capacity to add inference replicas.",
            "Place new replicas on healthy R-8 capacity.",
            "Hold new batch placements until latency stabilizes.",
        ]
    return [action.description]


def _evidence(findings: list[SituationalFinding], top_domains: list[DomainRisk]) -> list[str]:
    bullets = []
    for finding in findings[:3]:
        bullets.append(f"{finding.title}: {'; '.join(finding.evidence[:2])}")
    for risk in top_domains[:2]:
        bullets.append(f"{risk.domain} risk {risk.score:.0f}/100: {'; '.join(risk.evidence[:2])}")
    return bullets[:5]


def _if_no_action(scenario_id: str, eta: float | None) -> str:
    eta_text = f" in about {eta:.0f} minutes" if eta is not None else ""
    if scenario_id in {"cascade", "override_learning"}:
        return f"R-3 likely crosses from controllable degradation into SLA-impacting throttling{eta_text}."
    if scenario_id == "gpu_health":
        return f"The suspect GPU may force an unplanned job failure or emergency drain{eta_text}."
    return f"The inference service likely breaches p95/p99 latency SLOs{eta_text}."
