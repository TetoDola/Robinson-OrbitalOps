from __future__ import annotations

from ..models import (
    AgentFinding,
    MissionAction,
    MissionActionType,
    MissionPatch,
    SEVERITY_RANK,
    Severity,
    TelemetrySnapshot,
)


class CommanderAgent:
    name = "Commander Agent"

    def propose_patch(self, snapshot: TelemetrySnapshot, findings: list[AgentFinding]) -> MissionPatch:
        ranked = sorted(findings, key=lambda finding: (SEVERITY_RANK[finding.severity], finding.confidence), reverse=True)
        severe = [f for f in ranked if f.severity in {Severity.HIGH, Severity.CRITICAL}]
        actions: list[MissionAction] = []

        def add(action_type: MissionActionType, target: str, reason: str, **parameters):
            if not any(a.action_type == action_type and a.target == target for a in actions):
                actions.append(MissionAction(action_type=action_type, target=target, parameters=parameters, reason=reason))

        titles = " | ".join(f.title for f in severe)
        if "checkpoint" in titles.lower() or snapshot.ecc_uncorrected_errors:
            add(MissionActionType.MARK_CHECKPOINT_SUSPECT, snapshot.checkpoint_latest_id, "Latest checkpoint overlaps ECC/radiation risk.")
            add(MissionActionType.PRIORITIZE_DOWNLINK_HASHES, snapshot.checkpoint_latest_id, "Ground needs compact integrity evidence before full checkpoint.")
        if snapshot.ecc_uncorrected_errors:
            add(MissionActionType.CORDON_GPU, snapshot.node_id, "Uncorrected ECC makes this GPU unsafe for trusted continuation.")
            add(MissionActionType.REQUEST_HUMAN_REVIEW, "mission-control", "Rollback or continuation after ECC must be approved.")
        if snapshot.gpu_temperature_celsius > 85 or snapshot.battery_percent < 35:
            add(MissionActionType.LOWER_GPU_POWER_LIMIT, snapshot.node_id, "Thermal and power margins are both constrained.", limit_percent=60)
        if snapshot.gpu_temperature_celsius > 95:
            add(MissionActionType.ENTER_COOLDOWN_MODE, snapshot.node_id, "GPU temperature has crossed critical threshold.")
        if snapshot.downlink_window_seconds:
            add(MissionActionType.PRIORITIZE_DOWNLINK_MANIFEST, snapshot.checkpoint_latest_id, "Manifest is cheap and unlocks ground triage.")
            add(MissionActionType.DELAY_FULL_CHECKPOINT_DOWNLINK, snapshot.checkpoint_latest_id, "Full checkpoint exceeds safe bandwidth/trust constraints.")
        if snapshot.scheduler_state.value == "IDLE" and snapshot.gpu_utilization_percent > 70:
            add(MissionActionType.PAUSE_JOB, snapshot.job_id, "Scheduler and GPU truth disagree; freeze before state diverges further.")
        add(MissionActionType.INCREASE_CHECKPOINT_FREQUENCY, snapshot.job_id, "Capture recovery points before derating or cooldown.")

        if not severe:
            summary = "Continue nominal monitoring"
            rationale = "No high or critical mission constraint is active."
            risk_reduction = 12
            cost = 8
            approval = False
        else:
            summary = "Mission patch to preserve training integrity through radiation, thermal, power, and downlink conflict"
            rationale = (
                "The safest path is to avoid trusting the suspect checkpoint, reduce power/thermal stress, "
                "send compact integrity evidence first, and require human approval before rollback or continuation."
            )
            risk_reduction = min(95, 34 + 12 * len(severe))
            cost = min(80, 18 + 7 * len(actions))
            approval = any(f.requires_human_approval or f.severity == Severity.CRITICAL for f in severe)

        return MissionPatch(
            summary=summary,
            rationale=rationale,
            actions=actions,
            risk_reduction_score=risk_reduction,
            operational_cost_score=cost,
            requires_human_approval=approval,
        )
