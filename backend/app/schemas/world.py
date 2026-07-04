"""World-state response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class WorldStateResponse(BaseModel):
    version: int
    scenario_run_id: str | None
    updated_by: str
    updated_at: datetime
    state: dict[str, Any]
