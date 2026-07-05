"""Agent status response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AgentStatusItem(BaseModel):
    agent: str
    display_name: str
    status: str
    phase: str
    severity: str
    message: str
    updated_at: datetime
    linked_mission_patch_id: Optional[str] = None


class AgentsStatusResponse(BaseModel):
    agents: list[AgentStatusItem]


class AgentFindingItem(BaseModel):
    id: str
    agent_name: str
    severity: str
    confidence: float
    affected_assets: list[str]
    finding: str
    evidence: list[str]
    risk: Optional[str] = None
    recommended_actions: list[str]
    status: str
    created_at: datetime


class AgentFindingsResponse(BaseModel):
    findings: list[AgentFindingItem]
