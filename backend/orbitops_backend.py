from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.database import OrbitOpsDatabase
from app.models import ActionApprovalRequest, OperatorFeedback, PredictiveAgentRequest, RandomSimulationConfig
from app.services.telemetry_service import TelemetryService
from app.simulator.telemetry_simulator import TelemetrySimulator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


app = FastAPI(
    title="OrbitOps Agent Backend",
    version="2.0.0",
    description="Single-entry backend for the multimodal autonomous OrbitOps agent.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

database = OrbitOpsDatabase()
telemetry = TelemetryService(database, TelemetrySimulator())
app.state.database = database
app.state.telemetry = telemetry

if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/")
async def root():
    index_html = FRONTEND_DIST / "index.html"
    if index_html.exists():
        return FileResponse(index_html)
    return {
        "service": "OrbitOps Agent Backend",
        "status": "ok",
        "api": ["/api/health", "/api/simulation/random/*", "/api/agents/*"],
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "orbitops-agent-backend"}


@app.post("/api/simulation/random/start")
def start_random_simulation(payload: RandomSimulationConfig):
    return telemetry.start_random_simulation(payload)


@app.post("/api/simulation/random/stop")
def stop_random_simulation():
    return telemetry.stop_random_simulation()


@app.get("/api/simulation/random/status")
def random_simulation_status():
    return telemetry.random_simulation_status()


@app.post("/api/simulation/random/step")
def random_simulation_step():
    snapshot = telemetry.step()
    return {
        "status": telemetry.random_simulation_status(),
        "snapshot": snapshot,
        "prediction": telemetry.predictive_stream_result(),
    }


@app.get("/api/agents/predict")
def predictive_agent_result():
    return telemetry.predictive_stream_result()


@app.post("/api/agents/predict")
async def predictive_agent_deep_analysis(payload: PredictiveAgentRequest):
    return await telemetry.predictive_deep_analysis(payload)


@app.post("/api/agents/chat")
async def predictive_agent_chat(payload: PredictiveAgentRequest):
    return await telemetry.predictive_chat(payload)


@app.post("/api/agents/feedback")
def predictive_agent_feedback(payload: OperatorFeedback):
    return telemetry.record_operator_feedback(payload)


@app.get("/api/agents/memory")
def predictive_agent_memory():
    return telemetry.agent_memory()


@app.get("/api/agents/training-examples")
def predictive_agent_training_examples():
    return telemetry.predictive_agent.export_training_examples()


@app.get("/api/agents/nemotron-training-pack")
def predictive_agent_nemotron_training_pack():
    return telemetry.nemotron_training_pack()


@app.post("/api/agents/actions/decision")
def predictive_agent_action_decision(payload: ActionApprovalRequest):
    return telemetry.decide_recommended_action(payload)


@app.get("/api/agents/stream")
async def predictive_agent_stream():
    async def event_stream():
        while True:
            telemetry.advance_if_running()
            result = telemetry.predictive_stream_result()
            yield f"event: predictive-agent\ndata: {json.dumps(result.model_dump(mode='json'))}\n\n"
            await asyncio.sleep(1.4)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    index_html = FRONTEND_DIST / "index.html"
    if index_html.exists():
        return FileResponse(index_html)
    raise HTTPException(status_code=404, detail="Frontend build not found")
