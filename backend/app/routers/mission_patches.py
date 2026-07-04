"""Mission patch and approval routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEMO_SCENARIO_RUN_ID, StreamName
from app.db.models import Approval, Command, MissionPatch
from app.db.session import get_session
from app.services.event_bus import publish_stream_event

router = APIRouter(tags=["mission-patches"])


class ApprovalRequest(BaseModel):
    operator_id: str = "demo-operator"
    operator_note: str | None = None


@router.get("/mission-patches")
async def list_mission_patches(session: AsyncSession = Depends(get_session)) -> dict:
    result = await session.execute(select(MissionPatch).order_by(MissionPatch.created_at.desc()))
    return {"mission_patches": [_patch_payload(row) for row in result.scalars().all()]}


@router.get("/mission-patches/active")
async def active_mission_patch(session: AsyncSession = Depends(get_session)) -> dict:
    result = await session.execute(
        select(MissionPatch)
        .where(MissionPatch.status.in_(["pending_approval", "approved", "executing"]))
        .order_by(MissionPatch.created_at.desc())
    )
    patch = result.scalars().first()
    if patch is None:
        return {"mission_patch": None}
    return {"mission_patch": _patch_payload(patch)}


@router.get("/mission-patches/{patch_id}")
async def get_mission_patch(patch_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    patch_result = await session.execute(select(MissionPatch).where(MissionPatch.id == patch_id).with_for_update())
    patch = patch_result.scalar_one_or_none()
    if patch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission patch not found.")
    return {"mission_patch": _patch_payload(patch)}


@router.post("/mission-patches/{patch_id}/approve")
async def approve_mission_patch(
    patch_id: str,
    body: ApprovalRequest | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    patch = await session.get(MissionPatch, patch_id)
    if patch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission patch not found.")
    if patch.status not in {"pending_approval", "approved"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Patch is {patch.status}.")

    operator_id = body.operator_id if body else "demo-operator"
    key = idempotency_key or f"approval:{patch_id}:{operator_id}:approved"
    existing_approval = await session.execute(select(Approval).where(Approval.idempotency_key == key))
    approval = existing_approval.scalar_one_or_none()
    created_approval = approval is None

    if approval is None:
        approval = Approval(
            scenario_run_id=DEMO_SCENARIO_RUN_ID,
            mission_patch_id=patch.id,
            status="approved",
            operator_id=operator_id,
            operator_note=body.operator_note if body else None,
            idempotency_key=key,
            decided_at=datetime.now(timezone.utc),
        )
        session.add(approval)

    patch.status = "approved"
    patch.updated_at = datetime.now(timezone.utc)

    commands = []
    created_commands = 0
    for index, action in enumerate(patch.actions):
        action_type = action["type"]
        command_key = f"command:{patch.id}:{index}:{action_type}:{action.get('node_id') or action.get('job_id') or 'global'}"
        existing_command = await session.execute(select(Command).where(Command.idempotency_key == command_key))
        command = existing_command.scalar_one_or_none()
        if command is None:
            command = Command(
                scenario_run_id=DEMO_SCENARIO_RUN_ID,
                mission_patch_id=patch.id,
                action_type=action_type,
                target_asset_id=action.get("node_id") or action.get("job_id"),
                status="queued",
                input=action,
                result={},
                idempotency_key=command_key,
            )
            session.add(command)
            created_commands += 1
        commands.append(command)

    await session.commit()
    if created_approval or created_commands:
        await publish_stream_event(
            StreamName.command_requests.value,
            {
                "type": "command.batch_created",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"mission_patch_id": patch.id, "command_count": len(commands)},
            },
        )
        await publish_stream_event(
            StreamName.ui_events.value,
            {
                "type": "mission_patch.approved",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"id": patch.id, "status": "approved"},
            },
        )
    return {"mission_patch": _patch_payload(patch), "commands_created": created_commands}


def _patch_payload(patch: MissionPatch) -> dict:
    return {
        "id": patch.id,
        "incident_id": patch.incident_id,
        "severity": patch.severity,
        "status": patch.status,
        "summary": patch.summary,
        "evidence": patch.evidence,
        "actions": patch.actions,
        "rollback_plan": patch.rollback_plan,
        "approval_required": patch.approval_required,
    }
