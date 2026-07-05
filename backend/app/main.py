from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .api import routes_agents, routes_incidents, routes_patches, routes_science, routes_telemetry
from .database import OrbitOpsDatabase
from .models import SEVERITY_RANK, Severity
from .services.patch_service import PatchService
from .services.telemetry_service import TelemetryService
from .simulator.telemetry_simulator import TelemetrySimulator


app = FastAPI(
    title="OrbitOps API",
    version="1.0.0",
    description="Multi-agent command center for orbital GPU infrastructure.",
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
patches = PatchService(database, telemetry)
app.state.database = database
app.state.telemetry = telemetry
app.state.patches = patches

app.include_router(routes_telemetry.router)
app.include_router(routes_agents.router)
app.include_router(routes_incidents.router)
app.include_router(routes_patches.router)
app.include_router(routes_science.router)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/")
async def root():
    index_html = FRONTEND_DIST / "index.html"
    if index_html.exists():
        return FileResponse(index_html)
    return {
        "service": "OrbitOps API",
        "status": "ok",
        "frontend": "Run the frontend build or start Vite on http://127.0.0.1:5173",
        "api_docs": "http://127.0.0.1:8000/docs",
        "dashboard": "http://127.0.0.1:8000/api/dashboard",
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "orbitops"}


@app.get("/api/stream")
async def stream_dashboard():
    async def event_stream():
        while True:
            telemetry.advance_if_running()
            risk = telemetry.highest_severity()
            if SEVERITY_RANK[risk] >= SEVERITY_RANK[Severity.HIGH] and patches.latest() is None:
                patches.propose()
            state = telemetry.dashboard_state(patches.latest())
            yield f"event: dashboard\ndata: {json.dumps(state.model_dump(mode='json'))}\n\n"
            await asyncio.sleep(1.4)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    index_html = FRONTEND_DIST / "index.html"
    if index_html.exists():
        return FileResponse(index_html)
    raise HTTPException(
        status_code=404,
        detail="Frontend build not found. Run frontend build or start the Vite dev server.",
    )
