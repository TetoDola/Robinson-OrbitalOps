from __future__ import annotations

import asyncio

from app.routers.health import health
from app.schemas.health import HealthResponse


def test_health_route_returns_shape() -> None:
    response = asyncio.run(health())
    assert isinstance(response, HealthResponse)
    assert response.status == "ok"
    assert response.model_dump() == {"status": "ok"}
