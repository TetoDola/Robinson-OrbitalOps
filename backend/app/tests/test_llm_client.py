from __future__ import annotations

import asyncio

import httpx

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


def test_chat_completion_falls_back_to_openrouter(monkeypatch) -> None:
    monkeypatch.setattr(settings, "crusoe_enabled", True)
    monkeypatch.setattr(settings, "crusoe_api_key", "crusoe-key")
    monkeypatch.setattr(settings, "crusoe_base_url", "https://crusoe.test/v1")
    monkeypatch.setattr(settings, "openrouter_enabled", True)
    monkeypatch.setattr(settings, "openrouter_api_key", "openrouter-key")
    monkeypatch.setattr(settings, "openrouter_base_url", "https://openrouter.test/api/v1")
    monkeypatch.setattr(settings, "openrouter_model", "openrouter/auto")
    monkeypatch.setattr(settings, "openrouter_app_title", "Robinson Test")
    monkeypatch.setattr(settings, "openrouter_http_referer", "https://example.test")
    calls: list[dict] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "fallback response"}}]}

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict, json: dict) -> FakeResponse:
            calls.append({"url": url, "headers": headers, "json": json})
            if "crusoe.test" in url:
                raise httpx.ConnectError("primary unavailable")
            return FakeResponse()

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(
        llm_client._crusoe_chat_completion(
            model="primary-model",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=32,
            temperature=0.2,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
    )

    assert result is not None
    assert result["_robinson_provider"] == "openrouter"
    assert result["_robinson_model"] == "openrouter/auto"
    assert calls[0]["url"] == "https://crusoe.test/v1/chat/completions"
    assert calls[0]["json"]["model"] == "primary-model"
    assert calls[0]["json"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert calls[1]["url"] == "https://openrouter.test/api/v1/chat/completions"
    assert calls[1]["json"]["model"] == "openrouter/auto"
    assert "chat_template_kwargs" not in calls[1]["json"]
    assert calls[1]["headers"]["Authorization"] == "Bearer openrouter-key"
    assert calls[1]["headers"]["HTTP-Referer"] == "https://example.test"
    assert calls[1]["headers"]["X-OpenRouter-Title"] == "Robinson Test"
