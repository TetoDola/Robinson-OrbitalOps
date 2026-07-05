from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..models import ActionApprovalRequest, OperatorFeedback, PredictiveAgentRequest


router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/findings")
def agent_findings(request: Request):
    return request.app.state.telemetry.findings()


@router.post("/run")
def run_agents(request: Request):
    return request.app.state.telemetry.run_agents()


@router.get("/predict")
def predictive_agent_result(request: Request):
    return request.app.state.telemetry.predictive_stream_result()


@router.post("/predict")
async def predictive_agent_deep_analysis(payload: PredictiveAgentRequest, request: Request):
    return await request.app.state.telemetry.predictive_deep_analysis(payload)


@router.post("/chat")
async def predictive_agent_chat(payload: PredictiveAgentRequest, request: Request):
    return await request.app.state.telemetry.predictive_chat(payload)


@router.post("/feedback")
def predictive_agent_feedback(payload: OperatorFeedback, request: Request):
    return request.app.state.telemetry.record_operator_feedback(payload)


@router.get("/memory")
def predictive_agent_memory(request: Request):
    return request.app.state.telemetry.agent_memory()


@router.get("/training-examples")
def predictive_agent_training_examples(request: Request):
    return request.app.state.telemetry.predictive_agent.export_training_examples()


@router.get("/nemotron-training-pack")
def predictive_agent_nemotron_training_pack(request: Request):
    return request.app.state.telemetry.nemotron_training_pack()


@router.post("/actions/decision")
def predictive_agent_action_decision(payload: ActionApprovalRequest, request: Request):
    return request.app.state.telemetry.decide_recommended_action(payload)


@router.get("/stream")
async def predictive_agent_stream(request: Request):
    async def event_stream():
        while True:
            request.app.state.telemetry.advance_if_running()
            result = request.app.state.telemetry.predictive_stream_result()
            yield f"event: predictive-agent\ndata: {json.dumps(result.model_dump(mode='json'))}\n\n"
            await asyncio.sleep(1.4)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
