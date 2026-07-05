from __future__ import annotations

from app.agents.checkpoint_downlink_agent import CheckpointDownlinkRecoveryAgent
from app.agents.commander_agent import CommanderAgent
from app.agents.orbit_power_agent import OrbitPowerAgent
from app.agents.radiation_integrity_agent import RadiationIntegrityAgent
from app.agents.thermal_health_agent import ThermalHealthAgent
from app.models import MissionActionType
from app.simulator.scenarios import scenario_snapshots


def test_commander_creates_patch_for_multi_domain_collision():
    snapshot = scenario_snapshots()[5]
    findings = []
    for agent in [
        ThermalHealthAgent(),
        OrbitPowerAgent(),
        RadiationIntegrityAgent(),
        CheckpointDownlinkRecoveryAgent(),
    ]:
        findings.extend(agent.analyze(snapshot))

    patch = CommanderAgent().propose_patch(snapshot, findings)
    action_types = {action.action_type for action in patch.actions}

    assert patch.requires_human_approval is True
    assert MissionActionType.MARK_CHECKPOINT_SUSPECT in action_types
    assert MissionActionType.LOWER_GPU_POWER_LIMIT in action_types
    assert MissionActionType.DELAY_FULL_CHECKPOINT_DOWNLINK in action_types
    assert patch.risk_reduction_score >= 70
