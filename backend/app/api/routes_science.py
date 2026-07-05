from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from ..science.reporting import format_scientific_report
from ..science.types import ScienceDataRequest


router = APIRouter(prefix="/api/science", tags=["science"])


@router.get("/results")
def scientific_results(request: Request):
    return request.app.state.telemetry.scientific_assessment()


@router.get("/report", response_class=PlainTextResponse)
def scientific_report(request: Request):
    return format_scientific_report(request.app.state.telemetry.scientific_assessment())


@router.post("/results")
def scientific_results_from_data(payload: ScienceDataRequest, request: Request):
    samples = payload.samples
    elapsed_minutes = payload.elapsed_minutes if payload.elapsed_minutes is not None else 0
    return request.app.state.telemetry.science_engine.assess(samples[-1], elapsed_minutes, samples)


@router.post("/report", response_class=PlainTextResponse)
def scientific_report_from_data(payload: ScienceDataRequest, request: Request):
    samples = payload.samples
    elapsed_minutes = payload.elapsed_minutes if payload.elapsed_minutes is not None else 0
    assessment = request.app.state.telemetry.science_engine.assess(samples[-1], elapsed_minutes, samples)
    return format_scientific_report(assessment)


@router.post("/ingest")
def ingest_scientific_data(payload: ScienceDataRequest, request: Request):
    samples = payload.samples
    elapsed_minutes = payload.elapsed_minutes if payload.elapsed_minutes is not None else 0
    return request.app.state.telemetry.ingest_science_samples(samples, elapsed_minutes)
