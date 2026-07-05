"""Simulator control request/response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SimulatorInjectRequest(BaseModel):
    image_data_url: str | None = None
    audio_data_url: str | None = None
    audio_mime_type: str | None = None
    audio_duration_s: float | None = None
    audio_notes: str | None = None
    asset_id: str = "node-c"
    source: str = "operator-sim"
    notes: str | None = None


class SimulatorInjectResponse(BaseModel):
    issue: str
    status: str
    world_state_version: int
    finding_ids: list[str]
    image_id: str | None = None
    audio_id: str | None = None
    mission_patch_id: str | None = None
    analysis_status: str | None = None
    model_result: dict[str, Any] | None = None
