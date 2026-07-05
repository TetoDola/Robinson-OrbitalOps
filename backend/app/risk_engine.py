from __future__ import annotations

from statistics import mean

from .models import ClusterState, DomainRisk, RiskForecast, RiskLevel, SituationalFinding


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalized_score(value: float, safe: float, danger: float) -> float:
    if danger == safe:
        return 0
    return clamp((value - safe) / (danger - safe) * 100, 0, 100)


def eta_to_threshold(current: float, slope: float, threshold: float) -> float | None:
    if slope <= 0 or current >= threshold:
        return 0 if current >= threshold else None
    return max(0, (threshold - current) / slope)


def risk_level(score: float) -> RiskLevel:
    if score >= 75:
        return "critical"
    if score >= 55:
        return "high"
    if score >= 35:
        return "watch"
    return "normal"


def _trend(score: float) -> str:
    if score >= 55:
        return "worsening"
    if score <= 25:
        return "stable"
    return "worsening"


def analyze_cluster(cluster: ClusterState) -> tuple[list[DomainRisk], RiskForecast, list[SituationalFinding]]:
    hot_rack = max(cluster.racks, key=lambda r: r.rack_inlet_temp_c)
    busiest_link = max(cluster.network_links, key=lambda l: l.congestion_score)
    worst_gpu = max(
        (gpu for rack in cluster.racks for node in rack.nodes for gpu in node.gpus),
        key=lambda gpu: gpu.ecc_corrected_errors + 10 * gpu.xid_errors,
    )

    thermal_risk = normalized_score(hot_rack.rack_inlet_temp_c, 28, 40) * 0.65
    thermal_risk += normalized_score(hot_rack.thermal_slope_c_per_min, 0.25, 1.3) * 0.35

    cooling_risk = normalized_score(100 - hot_rack.cooling_efficiency_pct, 8, 35) * 0.55
    cooling_risk += 30 if hot_rack.fan_response_status == "delayed" else 0
    cooling_risk += 55 if hot_rack.fan_response_status == "failed" else 0

    power_risk = normalized_score(hot_rack.pdu_load_pct, 70, 98) * 0.75
    power_risk += normalized_score(hot_rack.power_spike_rate, 1, 9) * 0.25

    queue_sla_risk = normalized_score(cluster.queue.inference_queue_depth, 60, 220) * 0.45
    queue_sla_risk += normalized_score(cluster.queue.latency_p95_ms, 650, 1600) * 0.40
    queue_sla_risk += normalized_score(cluster.queue.queue_growth_rate_per_min, 4, 24) * 0.15

    network_risk = normalized_score(busiest_link.congestion_score, 35, 90) * 0.45
    network_risk += normalized_score(busiest_link.retransmits_per_sec, 8, 95) * 0.35
    network_risk += normalized_score(busiest_link.nccl_allreduce_slowdown_pct, 5, 45) * 0.20

    gpu_health_risk = normalized_score(worst_gpu.ecc_corrected_errors, 5, 90) * 0.40
    gpu_health_risk += normalized_score(worst_gpu.xid_errors, 0, 4) * 0.45
    gpu_health_risk += normalized_score(100 - worst_gpu.gpu_utilization_pct, 5, 45) * 0.15

    memory_risk = mean(
        gpu.gpu_memory_used_pct for rack in cluster.racks for node in rack.nodes for gpu in node.gpus
    )
    memory_risk = normalized_score(memory_risk, 72, 95)

    storage_risk = normalized_score(cluster.storage.storage_latency_ms, 20, 140) * 0.55
    storage_risk += normalized_score(cluster.storage.checkpoint_risk_score, 25, 90) * 0.45

    placement_risk = normalized_score(
        sum(r.fragmented_gpu_slots for r in cluster.racks), 6, 24
    ) * 0.45
    placement_risk += normalized_score(cluster.queue.pending_high_priority_jobs, 0, 6) * 0.30
    placement_risk += normalized_score(sum(r.placement_failures for r in cluster.racks), 0, 8) * 0.25

    inference_service_risk = normalized_score(cluster.inference_service.model_backpressure_score, 20, 85) * 0.50
    inference_service_risk += normalized_score(cluster.inference_service.time_to_first_token_ms, 450, 1800) * 0.30
    inference_service_risk += normalized_score(100 - cluster.inference_service.kv_cache_hit_rate_pct, 12, 50) * 0.20

    operator_policy_risk = 15 if any("maintenance" in note.lower() for note in cluster.policy_notes) else 5

    raw_scores = {
        "thermal": thermal_risk,
        "cooling": cooling_risk,
        "power": power_risk,
        "queue_sla": queue_sla_risk,
        "network": network_risk,
        "gpu_health": gpu_health_risk,
        "memory": memory_risk,
        "storage": storage_risk,
        "placement": placement_risk,
        "inference_service": inference_service_risk,
        "operator_policy": operator_policy_risk,
    }
    scores = {key: clamp(value, 0, 100) for key, value in raw_scores.items()}
    high_domains = sum(1 for score in scores.values() if score > 70)
    cascade_bonus = min(20, 5 * high_domains)
    overall = clamp(
        0.18 * scores["thermal"]
        + 0.12 * scores["cooling"]
        + 0.10 * scores["power"]
        + 0.12 * scores["queue_sla"]
        + 0.12 * scores["network"]
        + 0.10 * scores["gpu_health"]
        + 0.08 * scores["storage"]
        + 0.08 * scores["placement"]
        + 0.06 * scores["inference_service"]
        + 0.04 * scores["operator_policy"]
        + cascade_bonus,
        0,
        100,
    )

    for rack in cluster.racks:
        rack.overall_risk_score = clamp(
            normalized_score(rack.rack_inlet_temp_c, 28, 40) * 0.45
            + normalized_score(rack.pdu_load_pct, 70, 98) * 0.30
            + normalized_score(rack.thermal_slope_c_per_min, 0.2, 1.3) * 0.25,
            0,
            100,
        )
        rack.risk_level = risk_level(rack.overall_risk_score)
        rack.eta_to_throttle_min = eta_to_threshold(
            rack.rack_inlet_temp_c, rack.thermal_slope_c_per_min, 41
        )

    domain_risks = [
        DomainRisk(
            domain=domain,
            score=round(score, 1),
            level=risk_level(score),
            trend=_trend(score),  # type: ignore[arg-type]
            evidence=_evidence_for_domain(domain, cluster, hot_rack, busiest_link, worst_gpu),
        )
        for domain, score in scores.items()
    ]
    domain_risks.append(
        DomainRisk(
            domain="cascade",
            score=round(overall, 1),
            level=risk_level(overall),
            trend="worsening" if high_domains >= 2 else "stable",
            evidence=[f"{high_domains} domains above 70/100", f"Composite risk {overall:.0f}/100"],
        )
    )

    forecast = RiskForecast(
        eta_to_throttle_min=eta_to_threshold(hot_rack.rack_inlet_temp_c, hot_rack.thermal_slope_c_per_min, 41),
        eta_to_sla_breach_min=cluster.queue.sla_breach_eta_min,
        eta_to_queue_saturation_min=eta_to_threshold(cluster.queue.inference_queue_depth, cluster.queue.queue_growth_rate_per_min, 250),
        eta_to_power_limit_min=eta_to_threshold(hot_rack.pdu_load_pct, max(1, hot_rack.power_spike_rate), 100),
        eta_to_network_congestion_min=eta_to_threshold(busiest_link.congestion_score, max(1, busiest_link.retransmits_per_sec / 20), 92),
        eta_to_checkpoint_safe_window_min=min((j.checkpoint_eta_min for j in cluster.jobs if j.status == "running"), default=None),
        eta_to_gpu_failure_risk_min=eta_to_threshold(worst_gpu.ecc_corrected_errors + worst_gpu.xid_errors * 12, 6, 95),
        risk_now=round(overall, 1),
        risk_plus_5=round(clamp(overall + high_domains * 3 + max(0, hot_rack.thermal_slope_c_per_min) * 5, 0, 100), 1),
        risk_plus_10=round(clamp(overall + high_domains * 6 + max(0, hot_rack.thermal_slope_c_per_min) * 9, 0, 100), 1),
        risk_plus_15=round(clamp(overall + high_domains * 9 + max(0, hot_rack.thermal_slope_c_per_min) * 13, 0, 100), 1),
    )

    findings = _build_findings(cluster, scores, hot_rack, busiest_link, worst_gpu, overall)
    return domain_risks, forecast, findings


def _evidence_for_domain(domain: str, cluster: ClusterState, hot_rack, busiest_link, worst_gpu) -> list[str]:
    if domain == "thermal":
        return [
            f"{hot_rack.rack_id} inlet {hot_rack.rack_inlet_temp_c:.1f}C",
            f"slope {hot_rack.thermal_slope_c_per_min:.2f}C/min",
        ]
    if domain == "cooling":
        return [
            f"{hot_rack.cooling_zone} efficiency {hot_rack.cooling_efficiency_pct:.0f}%",
            f"fan response {hot_rack.fan_response_status}",
        ]
    if domain == "power":
        return [f"{hot_rack.rack_id} PDU {hot_rack.pdu_load_pct:.0f}%", f"spike rate {hot_rack.power_spike_rate:.1f}/min"]
    if domain == "queue_sla":
        return [f"queue {cluster.queue.inference_queue_depth}", f"p95 {cluster.queue.latency_p95_ms:.0f}ms"]
    if domain == "network":
        return [
            f"{busiest_link.link_id} congestion {busiest_link.congestion_score:.0f}/100",
            f"retransmits {busiest_link.retransmits_per_sec:.0f}/sec",
        ]
    if domain == "gpu_health":
        return [f"{worst_gpu.gpu_id} ECC {worst_gpu.ecc_corrected_errors}", f"XID {worst_gpu.xid_errors}"]
    if domain == "storage":
        return [f"storage latency {cluster.storage.storage_latency_ms:.0f}ms", f"checkpoint ETA {cluster.storage.checkpoint_eta_min:.1f}m"]
    if domain == "placement":
        return [f"pending high-priority {cluster.queue.pending_high_priority_jobs}", "fragmentation rising"]
    if domain == "inference_service":
        return [
            f"TTFT {cluster.inference_service.time_to_first_token_ms:.0f}ms",
            f"backpressure {cluster.inference_service.model_backpressure_score:.0f}/100",
        ]
    if domain == "operator_policy":
        return cluster.policy_notes[-2:]
    return []


def _build_findings(cluster: ClusterState, scores: dict[str, float], hot_rack, busiest_link, worst_gpu, overall: float) -> list[SituationalFinding]:
    findings: list[SituationalFinding] = []
    if scores["thermal"] >= 45:
        findings.append(SituationalFinding(
            finding_id="thermal-slope",
            severity=risk_level(scores["thermal"]),
            entity=hot_rack.rack_id,
            title="Thermal rise is becoming predictive, not just elevated",
            description=f"{hot_rack.rack_id} is heating at {hot_rack.thermal_slope_c_per_min:.2f}C/min with delayed mitigation capacity nearby.",
            evidence=[f"inlet {hot_rack.rack_inlet_temp_c:.1f}C", f"outlet {hot_rack.rack_outlet_temp_c:.1f}C"],
        ))
    if scores["queue_sla"] >= 45:
        findings.append(SituationalFinding(
            finding_id="queue-sla",
            severity=risk_level(scores["queue_sla"]),
            entity="inference-service",
            title="Queue pressure is moving toward SLA breach",
            description=f"Queue depth is {cluster.queue.inference_queue_depth} and p95 latency is {cluster.queue.latency_p95_ms:.0f}ms.",
            evidence=[f"growth {cluster.queue.queue_growth_rate_per_min:.1f}/min", f"p99 {cluster.queue.latency_p99_ms:.0f}ms"],
        ))
    if scores["network"] >= 45:
        findings.append(SituationalFinding(
            finding_id="network-retransmits",
            severity=risk_level(scores["network"]),
            entity=busiest_link.link_id,
            title="Cross-rack network health is degrading",
            description=f"{busiest_link.source_rack}->{busiest_link.target_rack} shows retransmits and NCCL slowdown.",
            evidence=[f"{busiest_link.retransmits_per_sec:.0f} retransmits/sec", f"NCCL slowdown {busiest_link.nccl_allreduce_slowdown_pct:.0f}%"],
        ))
    if scores["gpu_health"] >= 45:
        findings.append(SituationalFinding(
            finding_id="gpu-health",
            severity=risk_level(scores["gpu_health"]),
            entity=worst_gpu.gpu_id,
            title="GPU health anomaly is accumulating",
            description=f"{worst_gpu.gpu_id} is no longer a clean placement target.",
            evidence=[f"ECC {worst_gpu.ecc_corrected_errors}", f"XID {worst_gpu.xid_errors}"],
        ))
    findings.append(SituationalFinding(
        finding_id="compound-risk",
        severity=risk_level(overall),
        entity=cluster.cluster_id,
        title="Composite operational risk forecast",
        description=f"The cluster risk model is at {overall:.0f}/100 because weak signals are aligning across domains.",
        evidence=[f"{domain}: {score:.0f}" for domain, score in scores.items() if score >= 55][:5],
    ))
    return findings[:5]
