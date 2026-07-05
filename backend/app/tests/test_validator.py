from __future__ import annotations

from app.models import MissionAction, MissionActionType, MissionPatch, Severity
from app.simulator.scenarios import scenario_snapshots
from app.validators.mission_patch_validator import MissionPatchValidator


def test_validator_blocks_resume_after_uncorrected_ecc_without_human_approval():
    snapshot = scenario_snapshots()[3]
    patch = MissionPatch(
        summary="Unsafe resume attempt",
        rationale="The job should not resume while ECC remains unresolved.",
        actions=[
            MissionAction(
                action_type=MissionActionType.RESUME_JOB,
                target=snapshot.job_id,
                reason="Operator requested resume.",
            )
        ],
        risk_reduction_score=10,
        operational_cost_score=5,
        requires_human_approval=False,
    )

    result = MissionPatchValidator().validate(
        patch,
        snapshot,
        highest_thermal_severity=Severity.CRITICAL,
        human_approved=False,
    )

    assert result.is_valid is False
    assert result.requires_human_approval is True
    assert result.blocked_reasons


def test_validator_allows_same_resume_with_human_approval_but_keeps_warnings():
    snapshot = scenario_snapshots()[3]
    patch = MissionPatch(
        summary="Approved resume attempt",
        rationale="Human approval is explicitly present for this validation path.",
        actions=[
            MissionAction(
                action_type=MissionActionType.RESUME_JOB,
                target=snapshot.job_id,
                reason="Operator requested controlled resume.",
            )
        ],
        risk_reduction_score=10,
        operational_cost_score=5,
        requires_human_approval=True,
    )

    result = MissionPatchValidator().validate(patch, snapshot, human_approved=True)

    assert result.is_valid is True
    assert result.warnings
