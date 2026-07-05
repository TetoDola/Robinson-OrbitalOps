from __future__ import annotations

from math import sin

from .models import (
    AcceptedAction,
    ClusterState,
    CoolingZoneState,
    GPUState,
    InferenceServiceState,
    JobState,
    NetworkLinkState,
    NodeState,
    PowerDomainState,
    QueueState,
    RackState,
    StorageState,
    TelemetryEvent,
    iso_now,
)


RACK_IDS = [f"R-{idx}" for idx in range(1, 9)]


def create_initial_cluster(scenario_id: str = "cascade") -> ClusterState:
    tick = 0
    racks = [_build_rack(rack_id, idx) for idx, rack_id in enumerate(RACK_IDS, start=1)]
    cluster = ClusterState(
        region="us-crusoe-demo-1",
        cluster_id="crusoe-gpu-prod-a",
        scenario_id=scenario_id,
        tick=tick,
        simulated_time_min=0,
        racks=racks,
        cooling_zones=[
            CoolingZoneState(cooling_zone="C-1", cooling_efficiency_pct=92, fan_response_status="normal", coolant_flow_pct=94, cooling_zone_status="normal"),
            CoolingZoneState(cooling_zone="C-2", cooling_efficiency_pct=92, fan_response_status="normal", coolant_flow_pct=93, cooling_zone_status="normal"),
            CoolingZoneState(cooling_zone="C-3", cooling_efficiency_pct=94, fan_response_status="normal", coolant_flow_pct=96, cooling_zone_status="normal"),
        ],
        power_domains=[
            PowerDomainState(power_domain="PDU-A", pdu_load_pct=72, rack_power_limit_kw=95, breaker_risk_score=12, psu_health_status="healthy"),
            PowerDomainState(power_domain="PDU-B", pdu_load_pct=70, rack_power_limit_kw=95, breaker_risk_score=10, psu_health_status="healthy"),
            PowerDomainState(power_domain="PDU-C", pdu_load_pct=67, rack_power_limit_kw=95, breaker_risk_score=8, psu_health_status="healthy"),
        ],
        network_links=_base_links(),
        storage=StorageState(
            checkpoint_write_mbps=700,
            read_mbps=1200,
            write_mbps=900,
            storage_latency_ms=24,
            object_store_error_rate=0.02,
            checkpoint_eta_min=3.0,
            checkpoint_risk_score=18,
        ),
        jobs=_base_jobs(),
        queue=QueueState(
            inference_queue_depth=42,
            queue_growth_rate_per_min=2.0,
            pending_jobs_count=5,
            pending_high_priority_jobs=1,
            request_rate_per_sec=620,
            latency_p50_ms=210,
            latency_p95_ms=540,
            latency_p99_ms=820,
            sla_breach_eta_min=None,
            error_rate_pct=0.05,
        ),
        inference_service=InferenceServiceState(
            model_name="mixtral-inference-prod",
            request_rate=620,
            tokens_per_sec=9200,
            time_to_first_token_ms=340,
            time_per_output_token_ms=32,
            kv_cache_hit_rate_pct=88,
            model_backpressure_score=14,
            replica_count=12,
            healthy_replicas=12,
        ),
    )
    populate_scenario(cluster)
    return cluster


def advance_cluster(cluster: ClusterState) -> list[TelemetryEvent]:
    cluster.tick += 1
    cluster.simulated_time_min = cluster.tick * 0.5
    populate_scenario(cluster)
    return telemetry_events(cluster)


def populate_scenario(cluster: ClusterState) -> None:
    _reset_to_baseline(cluster)
    scenario = cluster.scenario_id
    if scenario == "gpu_health":
        _apply_gpu_health_scenario(cluster)
    elif scenario == "sla_pressure":
        _apply_sla_pressure_scenario(cluster)
    elif scenario == "override_learning":
        _apply_override_learning_scenario(cluster)
    else:
        _apply_cascade_scenario(cluster)
    _apply_accepted_action_effects(cluster)
    _sync_aggregate_domains(cluster)


def telemetry_events(cluster: ClusterState) -> list[TelemetryEvent]:
    hot = max(cluster.racks, key=lambda rack: rack.rack_inlet_temp_c)
    link = max(cluster.network_links, key=lambda item: item.congestion_score)
    worst_gpu = max(
        (gpu for rack in cluster.racks for node in rack.nodes for gpu in node.gpus),
        key=lambda gpu: gpu.ecc_corrected_errors + 10 * gpu.xid_errors,
    )
    severity = "critical" if hot.rack_inlet_temp_c >= 38 or cluster.queue.latency_p95_ms > 1400 else "high" if hot.rack_inlet_temp_c >= 34 else "watch"
    return [
        TelemetryEvent(
            timestamp=iso_now(),
            tick=cluster.tick,
            entity=hot.rack_id,
            metric="rack_inlet_temp_c",
            value=round(hot.rack_inlet_temp_c, 1),
            unit="C",
            severity=severity,
            message=f"{hot.rack_id} inlet temp {hot.rack_inlet_temp_c:.1f}C, slope {hot.thermal_slope_c_per_min:.2f}C/min",
        ),
        TelemetryEvent(
            timestamp=iso_now(),
            tick=cluster.tick,
            entity="inference-service",
            metric="latency_p95_ms",
            value=round(cluster.queue.latency_p95_ms, 0),
            unit="ms",
            severity="high" if cluster.queue.latency_p95_ms > 1000 else "watch",
            message=f"Queue {cluster.queue.inference_queue_depth}, p95 {cluster.queue.latency_p95_ms:.0f}ms",
        ),
        TelemetryEvent(
            timestamp=iso_now(),
            tick=cluster.tick,
            entity=link.link_id,
            metric="retransmits_per_sec",
            value=round(link.retransmits_per_sec, 0),
            unit="/sec",
            severity="high" if link.retransmits_per_sec > 50 else "watch",
            message=f"{link.source_rack}->{link.target_rack} retransmits {link.retransmits_per_sec:.0f}/sec",
        ),
        TelemetryEvent(
            timestamp=iso_now(),
            tick=cluster.tick,
            entity=worst_gpu.gpu_id,
            metric="gpu_health",
            value=worst_gpu.ecc_corrected_errors + worst_gpu.xid_errors * 10,
            severity="high" if worst_gpu.xid_errors else "watch",
            message=f"{worst_gpu.gpu_id} ECC {worst_gpu.ecc_corrected_errors}, XID {worst_gpu.xid_errors}",
        ),
    ]


def _build_rack(rack_id: str, idx: int) -> RackState:
    cooling_zone = "C-1" if idx <= 3 else "C-2" if idx <= 6 else "C-3"
    power_domain = "PDU-A" if idx <= 3 else "PDU-B" if idx <= 6 else "PDU-C"
    network_zone = "NZ-A" if idx <= 4 else "NZ-B"
    nodes = []
    for node_idx in range(1, 4):
        node_id = f"{rack_id}/N-{node_idx}"
        nodes.append(NodeState(
            node_id=node_id,
            rack_id=rack_id,
            gpus=[
                GPUState(
                    gpu_id=f"{node_id}/GPU-{gpu_idx}",
                    gpu_temperature_c=64 + idx + gpu_idx,
                    gpu_utilization_pct=72,
                    gpu_memory_used_pct=68,
                    hbm_bandwidth_pct=62,
                    sm_occupancy_pct=70,
                    power_watts=590,
                    clock_mhz=1810,
                )
                for gpu_idx in range(1, 5)
            ],
        ))
    return RackState(
        rack_id=rack_id,
        cooling_zone=cooling_zone,
        power_domain=power_domain,
        network_zone=network_zone,
        nodes=nodes,
        rack_inlet_temp_c=25 + idx * 0.2,
        rack_outlet_temp_c=33 + idx * 0.3,
        cooling_efficiency_pct=92,
        fan_rpm=8200,
        coolant_flow_pct=94,
        rack_power_kw=58 + idx,
        pdu_load_pct=68 + idx,
        available_gpu_slots=8 if rack_id == "R-7" else 3,
        fragmented_gpu_slots=2 if rack_id != "R-7" else 0,
        safe_destination=rack_id == "R-7",
    )


def _base_links() -> list[NetworkLinkState]:
    return [
        NetworkLinkState(
            link_id="R-3:R-4",
            source_rack="R-3",
            target_rack="R-4",
            bandwidth_used_gbps=180,
            bandwidth_capacity_gbps=400,
            latency_ms=1.8,
            retransmits_per_sec=5,
            packet_loss_pct=0.01,
            nccl_allreduce_slowdown_pct=3,
            cross_rack_traffic_pct=22,
            congestion_score=18,
        ),
        NetworkLinkState(
            link_id="R-5:R-6",
            source_rack="R-5",
            target_rack="R-6",
            bandwidth_used_gbps=145,
            bandwidth_capacity_gbps=400,
            latency_ms=1.6,
            retransmits_per_sec=4,
            packet_loss_pct=0.01,
            nccl_allreduce_slowdown_pct=2,
            cross_rack_traffic_pct=18,
            congestion_score=15,
        ),
        NetworkLinkState(
            link_id="R-7:R-8",
            source_rack="R-7",
            target_rack="R-8",
            bandwidth_used_gbps=120,
            bandwidth_capacity_gbps=400,
            latency_ms=1.4,
            retransmits_per_sec=2,
            packet_loss_pct=0,
            nccl_allreduce_slowdown_pct=1,
            cross_rack_traffic_pct=12,
            congestion_score=10,
        ),
    ]


def _base_jobs() -> list[JobState]:
    return [
        JobState(
            job_id="J-104",
            job_name="foundation-train-priority",
            workload_type="training",
            priority="high",
            current_rack="R-3",
            current_node="R-3/N-1",
            gpu_count=8,
            can_migrate=True,
            migration_cost="high",
            checkpoint_eta_min=3.0,
            estimated_remaining_minutes=220,
            preemptible=False,
            power_kw=22,
            memory_requirement_pct=82,
            network_requirement_gbps=140,
            storage_requirement_mbps=450,
        ),
        JobState(
            job_id="J-184",
            job_name="low-priority-embedding-batch",
            workload_type="batch",
            priority="low",
            current_rack="R-3",
            current_node="R-3/N-2",
            gpu_count=4,
            can_migrate=True,
            migration_cost="low",
            checkpoint_eta_min=1.5,
            estimated_remaining_minutes=60,
            preemptible=True,
            power_kw=12,
            memory_requirement_pct=55,
            network_requirement_gbps=35,
            storage_requirement_mbps=120,
        ),
        JobState(
            job_id="J-209",
            job_name="realtime-inference-pool",
            workload_type="inference",
            priority="critical",
            current_rack="R-2",
            current_node="R-2/N-1",
            gpu_count=8,
            can_migrate=True,
            migration_cost="medium",
            checkpoint_eta_min=0,
            estimated_remaining_minutes=999,
            sla_target_ms=900,
            current_latency_p95_ms=540,
            preemptible=False,
            power_kw=18,
            memory_requirement_pct=64,
            network_requirement_gbps=80,
            storage_requirement_mbps=50,
        ),
        JobState(
            job_id="J-331",
            job_name="offline-eval-batch",
            workload_type="batch",
            priority="low",
            current_rack="R-7",
            current_node="R-7/N-2",
            gpu_count=4,
            can_migrate=True,
            migration_cost="low",
            checkpoint_eta_min=0.5,
            estimated_remaining_minutes=45,
            preemptible=True,
            power_kw=9,
            memory_requirement_pct=48,
            network_requirement_gbps=15,
            storage_requirement_mbps=90,
        ),
    ]


def _reset_to_baseline(cluster: ClusterState) -> None:
    t = cluster.simulated_time_min
    for idx, rack in enumerate(cluster.racks, start=1):
        rack.rack_inlet_temp_c = 25 + idx * 0.2 + sin(t / 5 + idx) * 0.25
        rack.rack_outlet_temp_c = rack.rack_inlet_temp_c + 8.1
        rack.cooling_efficiency_pct = 92
        rack.fan_rpm = 8200 + sin(t + idx) * 60
        rack.fan_response_status = "normal"
        rack.coolant_flow_pct = 94
        rack.cooling_zone_status = "normal"
        rack.thermal_slope_c_per_min = 0.08
        rack.rack_power_kw = 58 + idx + sin(t / 4 + idx) * 0.8
        rack.pdu_load_pct = 68 + idx
        rack.psu_health_status = "healthy"
        rack.power_spike_rate = 1.2
        rack.power_cap_active = False
        rack.breaker_risk_score = 12
        rack.available_gpu_slots = 8 if rack.rack_id == "R-7" else 3
        rack.fragmented_gpu_slots = 1 + (idx % 3)
        rack.placement_failures = 0
        rack.safe_destination = rack.rack_id in {"R-7", "R-8"}
        for node in rack.nodes:
            node.node_cordoned = False
            node.node_draining = False
            node.pending_pods = 0
            node.failed_pods = 0
            for gpu in node.gpus:
                gpu.gpu_temperature_c = rack.rack_inlet_temp_c + 39 + sin(t / 3) * 0.8
                gpu.gpu_utilization_pct = 72
                gpu.gpu_memory_used_pct = 68
                gpu.hbm_bandwidth_pct = 62
                gpu.sm_occupancy_pct = 70
                gpu.power_watts = 590
                gpu.clock_mhz = 1810
                gpu.throttle_reason = "none"
                gpu.ecc_corrected_errors = 0
                gpu.ecc_uncorrected_errors = 0
                gpu.xid_errors = 0
                gpu.gpu_health_status = "healthy"

    cluster.network_links = _base_links()
    cluster.storage.checkpoint_write_mbps = 700
    cluster.storage.read_mbps = 1200
    cluster.storage.write_mbps = 900
    cluster.storage.storage_latency_ms = 24
    cluster.storage.object_store_error_rate = 0.02
    cluster.storage.checkpoint_eta_min = max(0, 3.0 - t)
    cluster.storage.checkpoint_risk_score = 18
    cluster.queue.inference_queue_depth = 42
    cluster.queue.queue_growth_rate_per_min = 2
    cluster.queue.pending_jobs_count = 5
    cluster.queue.pending_high_priority_jobs = 1
    cluster.queue.request_rate_per_sec = 620
    cluster.queue.latency_p50_ms = 210
    cluster.queue.latency_p95_ms = 540
    cluster.queue.latency_p99_ms = 820
    cluster.queue.sla_breach_eta_min = None
    cluster.queue.error_rate_pct = 0.05
    cluster.inference_service.request_rate = 620
    cluster.inference_service.tokens_per_sec = 9200
    cluster.inference_service.time_to_first_token_ms = 340
    cluster.inference_service.time_per_output_token_ms = 32
    cluster.inference_service.kv_cache_hit_rate_pct = 88
    cluster.inference_service.model_backpressure_score = 14
    cluster.inference_service.replica_count = 12
    cluster.inference_service.healthy_replicas = 12
    for job in cluster.jobs:
        if job.status != "paused":
            job.status = "running"
        job.checkpoint_eta_min = max(0, job.checkpoint_eta_min - 0.5)


def _apply_cascade_scenario(cluster: ClusterState) -> None:
    t = cluster.simulated_time_min
    ramp = min(1, t / 12)
    r3 = _rack(cluster, "R-3")
    r3.rack_inlet_temp_c = 27.2 + 11.0 * ramp
    r3.rack_outlet_temp_c = r3.rack_inlet_temp_c + 10.8
    r3.thermal_slope_c_per_min = 0.2 + 1.1 * ramp
    r3.cooling_efficiency_pct = 92 - 27 * ramp
    r3.fan_response_status = "delayed" if t >= 4 else "normal"
    r3.coolant_flow_pct = 94 - 20 * ramp
    r3.pdu_load_pct = 72 + 24 * ramp
    r3.rack_power_kw = 62 + 24 * ramp
    r3.power_spike_rate = 1.5 + 7 * ramp
    r3.breaker_risk_score = 15 + 60 * ramp
    r3.fragmented_gpu_slots = 7
    r3.placement_failures = int(4 * ramp)
    for gpu in r3.nodes[0].gpus:
        gpu.gpu_temperature_c = r3.rack_inlet_temp_c + 39
        gpu.gpu_utilization_pct = 92
        gpu.gpu_memory_used_pct = 84
        gpu.power_watts = 690

    link = _link(cluster, "R-3:R-4")
    link.bandwidth_used_gbps = 180 + 160 * ramp
    link.latency_ms = 1.8 + 3.7 * ramp
    link.retransmits_per_sec = 6 + 82 * ramp
    link.packet_loss_pct = 0.01 + 0.7 * ramp
    link.nccl_allreduce_slowdown_pct = 3 + 36 * ramp
    link.cross_rack_traffic_pct = 22 + 52 * ramp
    link.congestion_score = 18 + 72 * ramp

    cluster.queue.inference_queue_depth = int(46 + 155 * ramp)
    cluster.queue.queue_growth_rate_per_min = 3 + 19 * ramp
    cluster.queue.latency_p50_ms = 220 + 330 * ramp
    cluster.queue.latency_p95_ms = 560 + 900 * ramp
    cluster.queue.latency_p99_ms = 820 + 1250 * ramp
    cluster.queue.sla_breach_eta_min = max(2, 13 - t) if t >= 3 else None
    cluster.queue.pending_jobs_count = 5 + int(9 * ramp)
    cluster.queue.pending_high_priority_jobs = 1 + int(4 * ramp)
    cluster.inference_service.time_to_first_token_ms = 360 + 850 * ramp
    cluster.inference_service.time_per_output_token_ms = 32 + 32 * ramp
    cluster.inference_service.kv_cache_hit_rate_pct = 88 - 20 * ramp
    cluster.inference_service.model_backpressure_score = 14 + 60 * ramp
    cluster.storage.storage_latency_ms = 24 + 52 * ramp
    cluster.storage.checkpoint_write_mbps = 700 - 260 * ramp
    cluster.storage.checkpoint_risk_score = 18 + 45 * ramp
    _job(cluster, "J-104").checkpoint_eta_min = max(0, 3 - t)
    _job(cluster, "J-184").checkpoint_eta_min = max(0, 1.5 - t)


def _apply_gpu_health_scenario(cluster: ClusterState) -> None:
    t = cluster.simulated_time_min
    ramp = min(1, t / 10)
    gpu = _gpu(cluster, "R-5/N-2/GPU-3")
    rack = _rack(cluster, "R-5")
    gpu.ecc_corrected_errors = int(4 + 92 * ramp)
    gpu.xid_errors = 1 if t >= 4 else 0
    gpu.gpu_utilization_pct = 93
    gpu.gpu_memory_used_pct = 91
    gpu.hbm_bandwidth_pct = 88
    gpu.clock_mhz = 1540 - 180 * ramp
    gpu.gpu_health_status = "degraded" if t >= 4 else "watch"
    rack.rack_inlet_temp_c = 29.2 + 2 * ramp
    rack.rack_power_kw = 66 + 5 * ramp
    cluster.storage.checkpoint_eta_min = max(0, 3 - t / 2)
    _job(cluster, "J-184").current_rack = "R-5"
    _job(cluster, "J-184").current_node = "R-5/N-2"
    _job(cluster, "J-184").priority = "medium"
    _job(cluster, "J-184").job_name = "feature-store-refresh"
    _job(cluster, "J-184").checkpoint_eta_min = max(0, 2.5 - t / 2)
    cluster.queue.pending_jobs_count = 7


def _apply_sla_pressure_scenario(cluster: ClusterState) -> None:
    t = cluster.simulated_time_min
    ramp = min(1, t / 9)
    cluster.queue.inference_queue_depth = int(55 + 190 * ramp)
    cluster.queue.queue_growth_rate_per_min = 4 + 24 * ramp
    cluster.queue.request_rate_per_sec = 650 + 1100 * ramp
    cluster.queue.latency_p50_ms = 220 + 420 * ramp
    cluster.queue.latency_p95_ms = 620 + 1160 * ramp
    cluster.queue.latency_p99_ms = 900 + 1600 * ramp
    cluster.queue.sla_breach_eta_min = max(1, 10 - t)
    cluster.queue.error_rate_pct = 0.05 + 0.6 * ramp
    cluster.queue.pending_jobs_count = 8 + int(7 * ramp)
    cluster.queue.pending_high_priority_jobs = 3 + int(4 * ramp)
    cluster.inference_service.request_rate = cluster.queue.request_rate_per_sec
    cluster.inference_service.time_to_first_token_ms = 360 + 1050 * ramp
    cluster.inference_service.time_per_output_token_ms = 34 + 42 * ramp
    cluster.inference_service.tokens_per_sec = 9200 - 2500 * ramp
    cluster.inference_service.model_backpressure_score = 18 + 70 * ramp
    _job(cluster, "J-331").current_rack = "R-7"
    _job(cluster, "J-331").gpu_count = 8
    _rack(cluster, "R-7").available_gpu_slots = 0
    _rack(cluster, "R-8").available_gpu_slots = 6


def _apply_override_learning_scenario(cluster: ClusterState) -> None:
    _apply_cascade_scenario(cluster)
    if "cooling unit C-2 under maintenance" not in cluster.policy_notes:
        cluster.policy_notes.append("cooling unit C-2 under maintenance")
    _rack(cluster, "R-3").cooling_zone = "C-2"
    _rack(cluster, "R-3").cooling_zone_status = "maintenance"


def _apply_accepted_action_effects(cluster: ClusterState) -> None:
    accepted_ids = {action.action_id for action in cluster.accepted_actions}
    if "act-cascade-bundle" in accepted_ids or "act-migrate-j184" in accepted_ids:
        r3 = _rack(cluster, "R-3")
        r7 = _rack(cluster, "R-7")
        r3.rack_inlet_temp_c -= 5.2
        r3.rack_outlet_temp_c -= 5.6
        r3.thermal_slope_c_per_min = max(-0.15, r3.thermal_slope_c_per_min - 0.9)
        r3.rack_power_kw -= 13
        r3.pdu_load_pct -= 13
        r3.power_cap_active = True
        r3.available_gpu_slots += 4
        r3.fragmented_gpu_slots = max(1, r3.fragmented_gpu_slots - 4)
        r3.nodes[1].node_cordoned = True
        r7.available_gpu_slots = max(0, r7.available_gpu_slots - 4)
        job = _job(cluster, "J-184")
        job.current_rack = "R-7"
        job.current_node = "R-7/N-2"
        job.status = "running"
        cluster.queue.inference_queue_depth = max(35, cluster.queue.inference_queue_depth - 62)
        cluster.queue.latency_p95_ms = max(520, cluster.queue.latency_p95_ms - 360)
        link = _link(cluster, "R-3:R-4")
        link.retransmits_per_sec = max(4, link.retransmits_per_sec - 50)
        link.congestion_score = max(12, link.congestion_score - 42)
        cluster.inference_service.model_backpressure_score = max(12, cluster.inference_service.model_backpressure_score - 30)
    if "act-quarantine-gpu" in accepted_ids:
        gpu = _gpu(cluster, "R-5/N-2/GPU-3")
        gpu.gpu_health_status = "quarantined"
        gpu.gpu_utilization_pct = 0
        gpu.power_watts = 70
        _rack(cluster, "R-5").nodes[1].node_draining = True
        _job(cluster, "J-184").current_rack = "R-7"
        _job(cluster, "J-184").current_node = "R-7/N-1"
        _job(cluster, "J-184").status = "running"
    if "act-scale-inference" in accepted_ids:
        _job(cluster, "J-331").status = "paused"
        cluster.inference_service.replica_count += 3
        cluster.inference_service.healthy_replicas += 3
        cluster.inference_service.model_backpressure_score = max(10, cluster.inference_service.model_backpressure_score - 42)
        cluster.queue.inference_queue_depth = max(30, cluster.queue.inference_queue_depth - 105)
        cluster.queue.latency_p95_ms = max(480, cluster.queue.latency_p95_ms - 620)
        _rack(cluster, "R-8").available_gpu_slots = max(0, _rack(cluster, "R-8").available_gpu_slots - 6)


def _sync_aggregate_domains(cluster: ClusterState) -> None:
    zones: dict[str, list] = {}
    domains: dict[str, list] = {}
    for rack in cluster.racks:
        zones.setdefault(rack.cooling_zone, []).append(rack)
        domains.setdefault(rack.power_domain, []).append(rack)
    cluster.cooling_zones = [
        CoolingZoneState(
            cooling_zone=zone,
            cooling_efficiency_pct=sum(r.cooling_efficiency_pct for r in racks) / len(racks),
            fan_response_status="failed" if any(r.fan_response_status == "failed" for r in racks) else "delayed" if any(r.fan_response_status == "delayed" for r in racks) else "normal",
            coolant_flow_pct=sum(r.coolant_flow_pct for r in racks) / len(racks),
            cooling_zone_status="maintenance" if any(r.cooling_zone_status == "maintenance" for r in racks) else "watch" if any(r.cooling_efficiency_pct < 75 for r in racks) else "normal",
        )
        for zone, racks in sorted(zones.items())
    ]
    cluster.power_domains = [
        PowerDomainState(
            power_domain=domain,
            pdu_load_pct=sum(r.pdu_load_pct for r in racks) / len(racks),
            rack_power_limit_kw=95,
            breaker_risk_score=sum(r.breaker_risk_score for r in racks) / len(racks),
            psu_health_status="degraded" if any(r.psu_health_status == "degraded" for r in racks) else "watch" if any(r.pdu_load_pct > 90 for r in racks) else "healthy",
        )
        for domain, racks in sorted(domains.items())
    ]


def _rack(cluster: ClusterState, rack_id: str) -> RackState:
    return next(r for r in cluster.racks if r.rack_id == rack_id)


def _job(cluster: ClusterState, job_id: str) -> JobState:
    return next(j for j in cluster.jobs if j.job_id == job_id)


def _link(cluster: ClusterState, link_id: str) -> NetworkLinkState:
    return next(l for l in cluster.network_links if l.link_id == link_id)


def _gpu(cluster: ClusterState, gpu_id: str) -> GPUState:
    for rack in cluster.racks:
        for node in rack.nodes:
            for gpu in node.gpus:
                if gpu.gpu_id == gpu_id:
                    return gpu
    raise KeyError(gpu_id)
