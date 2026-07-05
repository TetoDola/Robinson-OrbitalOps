from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import AgentFinding, Severity, TelemetrySnapshot


class BaseAgent(ABC):
    name: str

    @abstractmethod
    def analyze(self, snapshot: TelemetrySnapshot) -> list[AgentFinding]:
        raise NotImplementedError

    def finding(
        self,
        severity: Severity,
        confidence: float,
        title: str,
        summary: str,
        evidence: list[str],
        recommended_actions: list[str],
        affected_resources: list[str],
        requires_human_approval: bool = False,
    ) -> AgentFinding:
        return AgentFinding(
            agent_name=self.name,
            severity=severity,
            confidence=confidence,
            title=title,
            summary=summary,
            evidence=evidence,
            recommended_actions=recommended_actions,
            affected_resources=affected_resources,
            requires_human_approval=requires_human_approval,
        )
