from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request


router = APIRouter(prefix="/api/patches", tags=["patches"])


@router.get("/latest")
def latest_patch(request: Request):
    return request.app.state.patches.latest()


@router.post("/propose")
def propose_patch(request: Request):
    return request.app.state.patches.propose()


@router.post("/{patch_id}/approve")
def approve_patch(patch_id: str, request: Request):
    try:
        return request.app.state.patches.approve(patch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown patch {patch_id}") from exc


@router.post("/{patch_id}/reject")
def reject_patch(patch_id: str, request: Request):
    try:
        return request.app.state.patches.reject(patch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown patch {patch_id}") from exc


@router.post("/{patch_id}/execute")
def execute_patch(patch_id: str, request: Request):
    try:
        return request.app.state.patches.execute(patch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown patch {patch_id}") from exc
