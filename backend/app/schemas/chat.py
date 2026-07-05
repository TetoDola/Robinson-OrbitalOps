"""Operator chat request and response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ChatRole = Literal["user", "assistant"]


class ChatTurn(BaseModel):
    role: ChatRole
    content: str = Field(..., min_length=1, max_length=4000)


class OperatorChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)


class ChatContextSummary(BaseModel):
    scenario: str | None = None
    world_version: int | None = None
    agent_count: int
    open_findings: int
    incident_count: int = 0
    mission_patch_count: int = 0
    command_count: int = 0
    queued_commands: int = 0
    running_commands: int = 0
    succeeded_commands: int = 0
    active_patch_id: str | None = None
    active_patch_status: str | None = None


class OperatorChatResponse(BaseModel):
    message: ChatTurn
    source: Literal["crusoe", "openrouter", "deterministic"]
    model: str | None = None
    context: ChatContextSummary
