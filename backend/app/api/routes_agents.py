from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/findings")
def agent_findings(request: Request):
    return request.app.state.telemetry.findings()


@router.post("/run")
def run_agents(request: Request):
    return request.app.state.telemetry.run_agents()
