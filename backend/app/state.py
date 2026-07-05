from __future__ import annotations

from threading import RLock

from .action_generator import generate_candidate_actions
from .models import (
    AgentRecommendation,
    CandidateAction,
    ClusterState,
    DomainRisk,
    RiskForecast,
    SituationalFinding,
    TelemetryEvent,
    UIState,
)
from .crusoe_client import crusoe_configured, mock_mode
from .risk_engine import analyze_cluster
from .scenarios import SCENARIOS
from .simulator import advance_cluster, create_initial_cluster, telemetry_events


class RuntimeState:
    def __init__(self) -> None:
        self._lock = RLock()
        self.cluster: ClusterState = create_initial_cluster("cascade")
        self.domain_risks: list[DomainRisk] = []
        self.forecast: RiskForecast
        self.findings: list[SituationalFinding] = []
        self.candidate_actions: list[CandidateAction] = []
        self.recommendation: AgentRecommendation | None = None
        self.outcome_timeline = []
        self.telemetry_feed: list[TelemetryEvent] = []
        for _ in range(20):
            self.telemetry_feed = (advance_cluster(self.cluster) + self.telemetry_feed)[:80]
        self._recompute()

    def reset(self, scenario_id: str | None = None) -> UIState:
        with self._lock:
            self.cluster = create_initial_cluster(scenario_id or self.cluster.scenario_id)
            self.recommendation = None
            self.outcome_timeline = []
            self.telemetry_feed = telemetry_events(self.cluster)
            self._recompute()
            return self.ui_state()

    def set_scenario(self, scenario_id: str) -> UIState:
        return self.reset(scenario_id)

    def tick(self) -> UIState:
        with self._lock:
            events = advance_cluster(self.cluster)
            self.telemetry_feed = (events + self.telemetry_feed)[:80]
            self._recompute()
            if self.recommendation and self.recommendation.recommended_action_id not in {
                action.action_id for action in self.candidate_actions
            }:
                self.recommendation = None
            return self.ui_state()

    def set_recommendation(self, recommendation: AgentRecommendation) -> UIState:
        with self._lock:
            self.recommendation = recommendation
            return self.ui_state()

    def add_outcome(self, outcome) -> UIState:
        with self._lock:
            self.outcome_timeline = [outcome] + self.outcome_timeline
            self.recommendation = None
            self._recompute()
            return self.ui_state()

    def ui_state(self) -> UIState:
        return UIState(
            cluster=self.cluster,
            domain_risks=self.domain_risks,
            forecasts=self.forecast,
            findings=self.findings,
            candidate_actions=self.candidate_actions,
            recommendation=self.recommendation,
            outcome_timeline=self.outcome_timeline[:30],
            telemetry_feed=self.telemetry_feed[:80],
            scenarios=SCENARIOS,
            mock_mode=mock_mode(),
            crusoe_configured=crusoe_configured(),
        )

    def _recompute(self) -> None:
        self.domain_risks, self.forecast, self.findings = analyze_cluster(self.cluster)
        self.candidate_actions = generate_candidate_actions(self.cluster, self.domain_risks, self.forecast)
