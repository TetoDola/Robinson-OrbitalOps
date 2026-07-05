"""Radiation risk routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.radiation import RadiationRiskResponse
from app.services.radiation_risk import get_radiation_risk_for_state
from app.services.world_state import read_world_state

router = APIRouter(tags=["radiation"])


async def _build_radiation_response(session: AsyncSession) -> RadiationRiskResponse:
    world_state = await read_world_state(session)
    if world_state is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="World state is not seeded.",
        )

    generated_at = datetime.now(timezone.utc)
    risk = await get_radiation_risk_for_state(world_state.state, generated_at.isoformat())
    satellite = world_state.state.get("satellite") or {}
    return RadiationRiskResponse(
        generatedAt=generated_at,
        satelliteId=satellite.get("id"),
        radiationRisk=risk,
    )


@router.get("/radiation-risk", response_model=RadiationRiskResponse)
async def get_radiation_risk(session: AsyncSession = Depends(get_session)) -> RadiationRiskResponse:
    return await _build_radiation_response(session)


@router.get("/api/radiation-risk", response_model=RadiationRiskResponse)
async def get_api_radiation_risk(session: AsyncSession = Depends(get_session)) -> RadiationRiskResponse:
    return await _build_radiation_response(session)
