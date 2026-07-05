from __future__ import annotations

from ..database import OrbitOpsDatabase
from ..models import AgentFinding, Incident, SEVERITY_RANK, Severity


class IncidentService:
    def __init__(self, database: OrbitOpsDatabase) -> None:
        self.database = database
        self._incidents: list[Incident] = []

    def sync_from_findings(self, findings: list[AgentFinding]) -> list[Incident]:
        active = [finding for finding in findings if SEVERITY_RANK[finding.severity] >= SEVERITY_RANK[Severity.HIGH]]
        incidents = [
            Incident(
                severity=finding.severity,
                title=finding.title,
                summary=finding.summary,
                source_agents=[finding.agent_name],
            )
            for finding in active
        ]
        self._incidents = incidents
        for incident in incidents:
            self.database.insert_model(
                "incidents",
                incident,
                {
                    "incident_id": incident.incident_id,
                    "created_at": incident.timestamp,
                    "severity": incident.severity.value,
                },
            )
        return incidents

    def list_incidents(self) -> list[Incident]:
        return self._incidents
