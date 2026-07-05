from __future__ import annotations

from fastapi import APIRouter, Request

from ..models import RandomSimulationConfig


router = APIRouter(prefix="/api/simulation", tags=["simulation"])


@router.post("/random/start")
def start_random_simulation(payload: RandomSimulationConfig, request: Request):
    return request.app.state.telemetry.start_random_simulation(payload)


@router.post("/random/stop")
def stop_random_simulation(request: Request):
    return request.app.state.telemetry.stop_random_simulation()


@router.get("/random/status")
def random_simulation_status(request: Request):
    return request.app.state.telemetry.random_simulation_status()


@router.post("/random/step")
def random_simulation_step(request: Request):
    snapshot = request.app.state.telemetry.step()
    return {
        "status": request.app.state.telemetry.random_simulation_status(),
        "snapshot": snapshot,
        "prediction": request.app.state.telemetry.predictive_stream_result(),
    }
