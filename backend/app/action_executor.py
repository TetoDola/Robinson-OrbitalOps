from __future__ import annotations

from uuid import uuid4

from .models import AcceptedAction, ActionOutcome, CandidateAction, ClusterState, iso_now
from .risk_engine import analyze_cluster
from .simulator import populate_scenario


def accept_action(cluster: ClusterState, action: CandidateAction, advisory_id: str) -> ActionOutcome:
    before = analyze_cluster(cluster)[1].risk_now
    cluster.accepted_actions.append(
        AcceptedAction(
            advisory_id=advisory_id,
            action_id=action.action_id,
            timestamp=iso_now(),
        )
    )
    populate_scenario(cluster)
    after = analyze_cluster(cluster)[1].risk_now
    return ActionOutcome(
        outcome_id=str(uuid4())[:8],
        timestamp=iso_now(),
        tick=cluster.tick,
        title=f"Accepted: {action.title}",
        description=_outcome_description(action),
        risk_before=before,
        risk_after=after,
    )


def _outcome_description(action: CandidateAction) -> str:
    if action.action_id == "act-cascade-bundle":
        return "J-184 moved to R-7, R-3 cordoned for new placements, and power cap applied."
    if action.action_id == "act-quarantine-gpu":
        return "R-5/N-2/GPU-3 quarantined after checkpoint and workload rescheduled."
    if action.action_id == "act-scale-inference":
        return "Low-priority batch paused and inference replicas added on healthy capacity."
    return action.description
