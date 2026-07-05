from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..models import Severity, TelemetrySnapshot


class CalculationMetric(BaseModel):
    name: str
    value: float | int | str
    unit: str = ""
    interpretation: str


class ModulePredictionResult(BaseModel):
    module_id: str
    module_name: str
    severity: Severity
    risk_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    prediction_horizon_minutes: int
    result: str
    predicted_event: str
    action_level: str
    dashboard_summary: str
    metrics: list[CalculationMetric]
    recommended_decision: str
    formula_summary: list[str]
    evidence: dict[str, Any] = Field(default_factory=dict)
    formulas: dict[str, Any] = Field(default_factory=dict)
    recommended_actions: list[dict[str, Any]] = Field(default_factory=list)
    requires_human_approval: bool = False


class ScientificAssessment(BaseModel):
    timestamp: str
    mission_clock: str
    orbit_phase: str
    data_mode: str
    samples_used: int
    trend_window_minutes: float
    overall_risk_score: float = Field(ge=0, le=100)
    overall_severity: Severity
    primary_risk_score: float = Field(ge=0, le=100)
    compound_risk_score: float = Field(ge=0, le=100)
    primary_driver: str
    global_action: str
    modules: list[ModulePredictionResult]


class ScienceDataRequest(BaseModel):
    samples: list[TelemetrySnapshot] = Field(min_length=1)
    elapsed_minutes: int | None = None
