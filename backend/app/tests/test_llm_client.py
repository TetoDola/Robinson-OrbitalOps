from __future__ import annotations

import asyncio

from app.config import settings
from app.services import llm_client
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


def test_thermal_analysis_sends_mp3_audio_part_to_omni(monkeypatch) -> None:
    monkeypatch.setattr(settings, "crusoe_enabled", True)
    monkeypatch.setattr(settings, "crusoe_api_key", "test-key")
    captured: dict = {}

    async def fake_completion(**kwargs):
        captured.update(kwargs)
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"audit_verdict":"warn","summary":"Audio and image support a fan anomaly.",'
                            '"confidence":0.88,"affected_assets":["node-c"],"evidence":["fan audio attached"],'
                            '"risk":"cooling loop may be unstable","recommended_actions":[],"questions":[],'
                            '"needs_human_review":false}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(llm_client, "_crusoe_chat_completion", fake_completion)

    result = asyncio.run(
        llm_client.analyze_thermal_ir_image(
            "data:image/png;base64,iVBORw0KGgo=",
            audio_data_url="data:audio/mpeg;base64,SUQzBAAAAAAA",
            audio_mime_type="audio/mpeg",
            audio_duration_s=3.4,
            audio_notes="Synthetic fan surge with bearing whine.",
            state={"thermal": {"highest_temp_c": 91}, "nodes": [{"id": "node-c", "temp_c": 91}]},
            finding={"finding": "Thermal frame shows a hotspot on node-c."},
        )
    )

    content = captured["messages"][-1]["content"]
    assert content[0]["type"] == "image_url"
    assert content[1] == {
        "type": "input_audio",
        "input_audio": {"data": "SUQzBAAAAAAA", "format": "mp3"},
    }
    assert "attached fan audio clip" in content[2]["text"]
    assert '"duration_s": 3.4' in content[2]["text"]
    assert result is not None
    assert result["audio_included"] is True
