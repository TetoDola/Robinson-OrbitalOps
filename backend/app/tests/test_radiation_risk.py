from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.constants import CANONICAL_WORLD_STATE, DEMO_BASELINE_WORLD_STATE
from app.routers.radiation import _build_radiation_response
from app.services import radiation_risk
from app.services.radiation_risk import compute_radiation_risk


MOCK_ENVIRONMENT = {
    "sourceMode": "mock",
    "ingestStatus": "mock source",
    "solarWind": {"speedKms": 510, "densityPcc": 8.2, "btNt": 8.7, "bzNt": -4.1},
    "xrayFluxWattsM2": 0.0000021,
    "protonFluxPfu": 3.4,
    "kpIndex": 4.33,
    "protonEvent": False,
    "sources": ["test"],
}


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _WorldStateRow:
    version = 1
    scenario_run_id = "phase-1-run"
    updated_by = "test"
    updated_at = datetime.now(timezone.utc)

    def __init__(self, state: dict):
        self.state = state


class _Session:
    def __init__(self, state: dict):
        self._state = state

    async def execute(self, _statement):
        return _Result(_WorldStateRow(self._state))


def test_compute_radiation_risk_returns_visualization_payload() -> None:
    risk = compute_radiation_risk(CANONICAL_WORLD_STATE, "2026-07-05T00:00:00+00:00", MOCK_ENVIRONMENT)

    assert risk["radiationLevel"] in {"MEDIUM", "HIGH", "CRITICAL"}
    assert risk["legacyRadiationRisk"] in {"elevated", "high", "critical"}
    assert risk["visualization"]["frames"][0]["fluxCells"]
    assert risk["visualization"]["frames"][0]["zones"]
    assert len(risk["trajectory"]) == 13


def test_baseline_radiation_risk_is_lower_than_elevated_demo() -> None:
    elevated = compute_radiation_risk(CANONICAL_WORLD_STATE, "2026-07-05T00:00:00+00:00", MOCK_ENVIRONMENT)
    baseline = compute_radiation_risk(DEMO_BASELINE_WORLD_STATE, "2026-07-05T00:00:00+00:00", MOCK_ENVIRONMENT)

    assert baseline["radiationRiskScore"] < elevated["radiationRiskScore"]


def test_radiation_route_uses_current_world_state(monkeypatch) -> None:
    async def fake_get_radiation_risk_for_state(state: dict, generated_at: str | None = None):
        return {"radiationRiskScore": 42, "stateScenario": state["scenario"], "generatedAt": generated_at}

    monkeypatch.setattr(radiation_risk, "_environment_cache", None)
    monkeypatch.setattr("app.routers.radiation.get_radiation_risk_for_state", fake_get_radiation_risk_for_state)

    response = asyncio.run(_build_radiation_response(_Session(CANONICAL_WORLD_STATE)))

    assert response.satelliteId == "orbital-dc-01"
    assert response.radiationRisk["radiationRiskScore"] == 42
    assert response.radiationRisk["stateScenario"] == "phase-1-demo"
