"""Shared Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TimestampedModel(BaseModel):
    updated_at: datetime


class WsEnvelope(TimestampedModel):
    type: str = Field(..., examples=["world_state.updated"])
    payload: dict[str, Any] = Field(default_factory=dict)
