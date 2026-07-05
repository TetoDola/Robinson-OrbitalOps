from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter(prefix="/api/incidents", tags=["incidents"])


@router.get("")
def incidents(request: Request):
    return request.app.state.telemetry.incident_service.list_incidents()
