from __future__ import annotations

import asyncio

from app.agents.data_context import enrich_agent_world_state
from app.constants import DEMO_BASELINE_WORLD_STATE


def test_agent_world_state_enrichment_attaches_compact_radiation_context(monkeypatch) -> None:
    async def fake_get_radiation_risk_for_state(state: dict, generated_at: str | None = None):
        return {
            "radiationRiskScore": 78,
            "radiationLevel": "HIGH",
            "mainCause": "Van Allen",
            "recommendedAction": "migrate workload",
            "explanation": "test risk model",
            "components": {"vanAllenBelt": 0.7},
            "sourceMode": "mock",
            "generatedAt": generated_at,
            "legacyRadiationRisk": "high",
            "visualization": {"frames": ["large payload"]},
        }

    monkeypatch.setattr(
        "app.agents.data_context.get_radiation_risk_for_state",
        fake_get_radiation_risk_for_state,
    )

    enriched = asyncio.run(enrich_agent_world_state(DEMO_BASELINE_WORLD_STATE, "2026-07-05T00:00:00+00:00"))
    computed = enriched["radiation"]["computed_risk"]

    assert computed["available"] is True
    assert computed["radiationRiskScore"] == 78
    assert computed["radiationLevel"] == "HIGH"
    assert computed["mainCause"] == "Van Allen"
    assert "visualization" not in computed
    assert "computed_risk" not in DEMO_BASELINE_WORLD_STATE["radiation"]
