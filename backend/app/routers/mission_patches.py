"""Mission patch and approval routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEMO_SCENARIO_RUN_ID, StreamName
from app.db.models import Approval, Command, Incident, MissionPatch
from app.db.session import get_session
from app.services.outbox import enqueue_outbox_event, publish_outbox_events_by_keys

router = APIRouter(tags=["mission-patches"])


class ApprovalRequest(BaseModel):
    operator_id: str = "demo-operator"
    operator_note: str | None = None


class RejectRequest(BaseModel):
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
    operator_id = body.operator_id if body else "demo-operator"
    operator_note = body.operator_note if body else None
    patch, created_approval, created_commands, commands, outbox_keys = await approve_patch_transaction(
        session,
        patch_id=patch_id,
        operator_id=operator_id,
        operator_note=operator_note,
        idempotency_key=idempotency_key,
    )

    await publish_outbox_events_by_keys(outbox_keys)
    return {
        "mission_patch": _patch_payload(patch),
        "commands_created": created_commands,
        "commands": [_command_payload(command) for command in commands],
    }


@router.post("/mission-patches/{patch_id}/reject")
async def reject_mission_patch(
    patch_id: str,
    body: RejectRequest | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    operator_id = body.operator_id if body else "demo-operator"
    operator_note = body.operator_note if body else None
    patch, created_rejection, outbox_keys = await reject_patch_transaction(
        session,
        patch_id=patch_id,
        operator_id=operator_id,
        operator_note=operator_note,
        idempotency_key=idempotency_key,
    )

    await publish_outbox_events_by_keys(outbox_keys)
    return {"mission_patch": _patch_payload(patch), "rejection_created": created_rejection}


async def approve_patch_transaction(
    session: AsyncSession,
    *,
    patch_id: str,
    operator_id: str,
    operator_note: str | None,
    idempotency_key: str | None = None,
) -> tuple[MissionPatch, bool, int, list[Command], list[str]]:
    patch = await _locked_patch(session, patch_id)
    if patch.status == "approved":
        await _validate_reused_idempotency_key(session, idempotency_key, patch.id, "approved")
        commands = await _commands_for_patch(session, patch.id)
        return patch, False, 0, commands, []
    if patch.status != "pending_approval":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Patch is {patch.status}.")

    outbox_keys: list[str] = []
    key = idempotency_key or f"approval:{patch_id}:{operator_id}:approved"
    existing_approval = await session.execute(select(Approval).where(Approval.idempotency_key == key))
    approval = existing_approval.scalar_one_or_none()
    created_approval = approval is None
    if approval is not None:
        _validate_existing_decision(approval, patch.id, "approved")

    if approval is None:
        approval = Approval(
            scenario_run_id=DEMO_SCENARIO_RUN_ID,
            mission_patch_id=patch.id,
            status="approved",
            operator_id=operator_id,
            operator_note=operator_note,
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
                target_asset_id=_action_target_asset(action),
                status="queued",
                input=action,
                result={},
                idempotency_key=command_key,
            )
            session.add(command)
            created_commands += 1
        commands.append(command)

    if created_approval or created_commands:
        command_event_key = f"outbox:{patch.id}:command.batch_created"
        approval_event_key = f"outbox:{patch.id}:mission_patch.approved"
        await enqueue_outbox_event(
            session,
            stream=StreamName.command_requests.value,
            event_type="command.batch_created",
            payload={"mission_patch_id": patch.id, "command_count": len(commands)},
            idempotency_key=command_event_key,
        )
        await enqueue_outbox_event(
            session,
            stream=StreamName.ui_events.value,
            event_type="mission_patch.approved",
            payload={"id": patch.id, "status": "approved"},
            idempotency_key=approval_event_key,
        )
        outbox_keys.extend([command_event_key, approval_event_key])

    await session.commit()
    return patch, created_approval, created_commands, commands, outbox_keys


async def reject_patch_transaction(
    session: AsyncSession,
    *,
    patch_id: str,
    operator_id: str,
    operator_note: str | None,
    idempotency_key: str | None = None,
) -> tuple[MissionPatch, bool, list[str]]:
    patch = await _locked_patch(session, patch_id)
    if patch.status == "rejected":
        await _validate_reused_idempotency_key(session, idempotency_key, patch.id, "rejected")
        return patch, False, []
    if patch.status != "pending_approval":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Patch is {patch.status}.")

    outbox_keys: list[str] = []
    key = idempotency_key or f"approval:{patch_id}:{operator_id}:rejected"
    existing_rejection = await session.execute(select(Approval).where(Approval.idempotency_key == key))
    rejection = existing_rejection.scalar_one_or_none()
    created_rejection = rejection is None
    if rejection is not None:
        _validate_existing_decision(rejection, patch.id, "rejected")

    if rejection is None:
        rejection = Approval(
            scenario_run_id=DEMO_SCENARIO_RUN_ID,
            mission_patch_id=patch.id,
            status="rejected",
            operator_id=operator_id,
            operator_note=operator_note,
            idempotency_key=key,
            decided_at=datetime.now(timezone.utc),
        )
        session.add(rejection)

    patch.status = "rejected"
    patch.updated_at = datetime.now(timezone.utc)
    if patch.incident_id:
        incident = await session.get(Incident, patch.incident_id)
        if incident is not None:
            incident.status = "rejected"
            incident.updated_at = datetime.now(timezone.utc)
    rejection_event_key = f"outbox:{patch.id}:mission_patch.rejected"
    await enqueue_outbox_event(
        session,
        stream=StreamName.ui_events.value,
        event_type="mission_patch.rejected",
        payload={"id": patch.id, "status": "rejected"},
        idempotency_key=rejection_event_key,
    )
    outbox_keys.append(rejection_event_key)
    await session.commit()
    return patch, created_rejection, outbox_keys


async def _locked_patch(session: AsyncSession, patch_id: str) -> MissionPatch:
    patch_result = await session.execute(select(MissionPatch).where(MissionPatch.id == patch_id).with_for_update())
    patch = patch_result.scalar_one_or_none()
    if patch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission patch not found.")
    return patch


async def _commands_for_patch(session: AsyncSession, patch_id: str) -> list[Command]:
    result = await session.execute(select(Command).where(Command.mission_patch_id == patch_id).order_by(Command.created_at.asc()))
    return list(result.scalars().all())


def _action_target_asset(action: dict) -> str | None:
    return (
        action.get("node_id")
        or action.get("asset_id")
        or action.get("job_id")
        or action.get("checkpoint_id")
        or next(iter(action.get("asset_ids", [])), None)
    )


def _validate_existing_decision(decision: Approval, patch_id: str, status_value: str) -> None:
    if decision.mission_patch_id != patch_id or decision.status != status_value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used for a different mission patch decision.",
        )


async def _validate_reused_idempotency_key(
    session: AsyncSession,
    idempotency_key: str | None,
    patch_id: str,
    status_value: str,
) -> None:
    if not isinstance(idempotency_key, str):
        return
    existing_result = await session.execute(select(Approval).where(Approval.idempotency_key == idempotency_key))
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        _validate_existing_decision(existing, patch_id, status_value)


def _command_payload(command: Command) -> dict:
    return {
        "id": command.id,
        "mission_patch_id": command.mission_patch_id,
        "action_type": command.action_type,
        "target_asset_id": command.target_asset_id,
        "status": command.status,
        "input": command.input,
        "result": command.result,
    }


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
