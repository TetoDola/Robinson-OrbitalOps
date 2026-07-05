"""Agent status response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


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


class AgentRuntimeItem(BaseModel):
    agent: str
    display_name: str
    trigger_mode: str
    interval_seconds: int
    run_state: str
    last_run_at: datetime
    next_run_at: datetime
    seconds_until_next_run: int
    missed_runs: int
    last_result: str


class AgentsRuntimeResponse(BaseModel):
    agents: list[AgentRuntimeItem]


class ThermalImageInputRequest(BaseModel):
    image_data_url: str = Field(..., min_length=16)
    asset_id: str = "node-c"
    source: str = "operator-upload"
    notes: Optional[str] = None


class ThermalImageInputResponse(BaseModel):
    image_id: str
    asset_id: str
    analysis_status: str
    model_result: dict[str, Any] | None = None
    finding_id: str | None = None
    mission_patch_id: str | None = None
    world_state_version: int
