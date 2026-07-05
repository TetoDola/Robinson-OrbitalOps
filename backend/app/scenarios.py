from __future__ import annotations

from .models import SimulationScenario


SCENARIOS: list[SimulationScenario] = [
    SimulationScenario(
        scenario_id="cascade",
        name="Multi-domain cascade",
        description=(
            "R-3 heats faster than normal while cooling response, queue pressure, "
            "network retransmits, and power draw all worsen together."
        ),
        expected_recommendation=(
            "Wait for checkpoint if needed, migrate low-priority J-184 to R-7, "
            "cordon R-3, and apply a temporary power cap."
        ),
    ),
    SimulationScenario(
        scenario_id="gpu_health",
        name="GPU health anomaly",
        description=(
            "R-5/N-2/GPU-3 shows rising ECC and XID warnings while throughput drops "
            "under high utilization."
        ),
        expected_recommendation=(
            "Drain and quarantine the GPU after checkpoint, then reschedule the workload."
        ),
    ),
    SimulationScenario(
        scenario_id="sla_pressure",
        name="Queue / SLA pressure",
        description=(
            "Inference request rate spikes, queue depth and p95 latency rise, while "
            "low-priority batch work occupies healthy capacity."
        ),
        expected_recommendation=(
            "Preempt or migrate low-priority batch and scale inference replicas on a safe rack."
        ),
    ),
    SimulationScenario(
        scenario_id="override_learning",
        name="Override learning",
        description=(
            "A cooling intervention would normally be tempting, but operator feedback "
            "marks cooling unit C-2 as unavailable."
        ),
        expected_recommendation=(
            "Avoid cooling escalation after override and prefer migration plus power cap."
        ),
    ),
]


def get_scenario(scenario_id: str) -> SimulationScenario:
    for scenario in SCENARIOS:
        if scenario.scenario_id == scenario_id:
            return scenario
    return SCENARIOS[0]
