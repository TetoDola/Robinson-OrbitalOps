"""Incident routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Incident
from app.db.session import get_session

router = APIRouter(tags=["incidents"])


@router.get("/incidents")
async def list_incidents(session: AsyncSession = Depends(get_session)) -> dict:
    result = await session.execute(select(Incident).order_by(Incident.created_at.desc()))
    return {"incidents": [_incident_payload(row) for row in result.scalars().all()]}


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found.")
    return {"incident": _incident_payload(incident)}


def _incident_payload(incident: Incident) -> dict:
    return {
        "id": incident.id,
        "incident_key": incident.incident_key,
        "title": incident.title,
        "severity": incident.severity,
        "status": incident.status,
        "finding_ids": incident.finding_ids,
        "summary": incident.summary,
    }
