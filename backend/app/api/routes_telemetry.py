from __future__ import annotations

from fastapi import APIRouter, Request

from ..models import SEVERITY_RANK, Severity


router = APIRouter(prefix="/api", tags=["telemetry"])


@router.get("/telemetry/latest")
def latest_telemetry(request: Request):
    return request.app.state.telemetry.latest()


@router.get("/telemetry/history")
def telemetry_history(request: Request):
    return request.app.state.telemetry.history()


@router.get("/dashboard")
def dashboard(request: Request):
    return request.app.state.telemetry.dashboard_state(request.app.state.patches.latest())


@router.post("/simulator/start")
def simulator_start(request: Request):
    return request.app.state.telemetry.start()


@router.post("/simulator/stop")
def simulator_stop(request: Request):
    return request.app.state.telemetry.stop()


@router.post("/simulator/reset")
def simulator_reset(request: Request):
    request.app.state.patches._latest_patch = None
    return request.app.state.telemetry.reset()


@router.post("/simulator/step")
def simulator_step(request: Request):
    snapshot = request.app.state.telemetry.step()
    risk = request.app.state.telemetry.highest_severity()
    if SEVERITY_RANK[risk] >= SEVERITY_RANK[Severity.HIGH] and request.app.state.patches.latest() is None:
        request.app.state.patches.propose()
    return snapshot
