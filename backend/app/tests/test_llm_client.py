from __future__ import annotations

from app.services.llm_client import _normalize_thermal_analysis


def test_thermal_analysis_followups_are_fail_only() -> None:
    result = _normalize_thermal_analysis(
        {
            "audit_verdict": "pass",
            "summary": "Thermal frame supports the node-c hotspot.",
            "confidence": 0.91,
            "affected_assets": ["node-c"],
            "evidence": ["node-c is hottest"],
            "risk": "Thermal anomaly is supported.",
            "recommended_actions": ["mark_node_suspect", "run_health_check"],
            "questions": ["Ask the operator for another frame."],
            "needs_human_review": True,
        }
    )

    assert result["audit_verdict"] == "pass"
    assert result["recommended_actions"] == []
    assert result["questions"] == []
    assert result["needs_human_review"] is False


def test_thermal_analysis_fail_keeps_allowed_followups() -> None:
    result = _normalize_thermal_analysis(
        {
            "audit_verdict": "fail",
            "summary": "Thermal frame is too ambiguous for confirmation.",
            "confidence": 0.42,
            "affected_assets": ["node-c"],
            "evidence": ["image is low contrast"],
            "risk": "Finding may be unsupported.",
            "recommended_actions": ["snapshot_evidence", "kill_process"],
            "questions": ["Request a fresh IR frame."],
            "needs_human_review": False,
        }
    )

    assert result["audit_verdict"] == "fail"
    assert result["recommended_actions"] == ["snapshot_evidence"]
    assert result["questions"] == ["Request a fresh IR frame."]
    assert result["needs_human_review"] is True
