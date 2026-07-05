"""Radiation risk API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RadiationRiskResponse(BaseModel):
    generatedAt: datetime
    satelliteId: str | None
    radiationRisk: dict[str, Any]
