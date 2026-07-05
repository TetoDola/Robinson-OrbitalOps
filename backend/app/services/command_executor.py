"""Mock command executor for approved mission patches."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.constants import StreamName
from app.db.models import AgentFinding, AgentStatus, Command, Incident, MissionPatch
from app.db.session import session_context
from app.services.bootstrap import wait_for_database_ready, wait_for_redis_ready
from app.services.outbox import enqueue_outbox_event, publish_outbox_events_by_keys
from app.services.redis_client import get_redis
from app.services.world_state import write_world_state


def apply_action_to_state(action: dict) -> dict:
    action_type = action["type"]
    if action_type == "mark_checkpoint_suspect":
        return {"training": {"latest_checkpoint_status": "suspect", "quarantined_checkpoint": action["checkpoint_id"]}}
    if action_type == "rollback_training":
        return {
            "training": {
                "job_id": action["job_id"],
                "status": "recovering",
                "current_step": _checkpoint_step(action["checkpoint_id"]),
                "recovery_checkpoint": action["checkpoint_id"],
            }
        }
    if action_type == "cordon_node":
        return {"node_overrides": {action["node_id"]: {"status": "cordoned", "scope": action["scope"]}}}
    if action_type == "mark_node_suspect":
        return {"node_overrides": {action["node_id"]: {"status": "suspect", "reason": action["reason"]}}}
    if action_type == "snapshot_evidence":
        return {
            "forensics": {
                "snapshot_status": "captured",
                "asset_ids": action["asset_ids"],
                "include": action["include"],
            }
        }
    if action_type == "run_health_check":
        return {
            "verification": {
                "asset_id": action["asset_id"],
                "check_suite": action["check_suite"],
                "status": "passed",
            }
        }
    if action_type == "set_gpu_power_limit":
        return {"power": {"mode": "degraded_safe"}, "training": {"throughput_mode": "reduced_safe"}}
    if action_type == "increase_checkpoint_frequency":
        return {"training": {"checkpoint_interval_minutes": action["interval_minutes"]}}
    if action_type == "transfer_priority":
        return {
            "downlink": {
                "queue": action["send_first"] + [f"defer:{item}" for item in action["defer"]],
                "used_gb": 14.4,
            }
        }
    return {}


def _checkpoint_step(checkpoint_id: str) -> int:
    try:
        return int(checkpoint_id.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 0


async def execute_queued_commands_once(
    mission_patch_id: str | None = None,
    *,
    session_factory=session_context,
    state_writer=write_world_state,
    outbox_enqueuer=enqueue_outbox_event,
    outbox_publisher=publish_outbox_events_by_keys,
) -> int:
    outbox_keys: list[str] = []
    async with session_factory() as session:
        stmt = select(Command).where(Command.status == "queued")
        if mission_patch_id is not None:
            stmt = stmt.where(Command.mission_patch_id == mission_patch_id)
        stmt = stmt.order_by(Command.created_at.asc()).with_for_update(skip_locked=True)
        result = await session.execute(stmt)
        commands = list(result.scalars().all())
        outbox_keys = await execute_commands_in_session(
            session,
            commands,
            state_writer=state_writer,
            outbox_enqueuer=outbox_enqueuer,
        )
        await session.commit()

    await outbox_publisher(outbox_keys)
    return len(commands)


async def execute_commands_in_session(
    session,
    commands: list[Command],
    *,
    state_writer=write_world_state,
    outbox_enqueuer=enqueue_outbox_event,
) -> list[str]:
    """Apply queued commands and enqueue lifecycle events in the same DB transaction."""
    outbox_keys: list[str] = []
    patch_ids = {command.mission_patch_id for command in commands}
    for patch_id in patch_ids:
        mission_patch = await session.get(MissionPatch, patch_id)
        if mission_patch is not None and mission_patch.status == "approved":
            mission_patch.status = "executing"
            mission_patch.updated_at = datetime.now(timezone.utc)
            outbox_keys.extend(
                await _enqueue_event(
                    session,
                    outbox_enqueuer,
                    StreamName.ui_events.value,
                    "mission_patch.executing",
                    {"id": patch_id, "status": "executing"},
                    f"outbox:{patch_id}:mission_patch.executing",
                )
            )

    for command in commands:
        command.status = "running"
        command.updated_at = datetime.now(timezone.utc)
        outbox_keys.extend(
            await _enqueue_event(
                session,
                outbox_enqueuer,
                StreamName.ui_events.value,
                "command.started",
                {
                    "id": command.id,
                    "mission_patch_id": command.mission_patch_id,
                    "action_type": command.action_type,
                    "status": "running",
                },
                f"outbox:{command.id}:command.started",
            )
        )

        state_patch = apply_action_to_state(command.input)
        if state_patch:
            await state_writer(session, state_patch, updated_by="orbitops-executor", reason=command.action_type)
        command.status = "succeeded"
        command.result = {"verified": True, "message": f"{command.action_type} completed"}
        command.updated_at = datetime.now(timezone.utc)
        success_payload = {
            "id": command.id,
            "mission_patch_id": command.mission_patch_id,
            "action_type": command.action_type,
            "status": "succeeded",
            "result": command.result,
        }
        outbox_keys.extend(
            await _enqueue_event(
                session,
                outbox_enqueuer,
                StreamName.command_results.value,
                "command.succeeded",
                success_payload,
                f"outbox:{command.id}:command.succeeded:command_results",
            )
        )
        outbox_keys.extend(
            await _enqueue_event(
                session,
                outbox_enqueuer,
                StreamName.ui_events.value,
                "command.succeeded",
                success_payload,
                f"outbox:{command.id}:command.succeeded:ui_events",
            )
        )

    for patch_id in patch_ids:
        mission_patch = await session.get(MissionPatch, patch_id)
        if mission_patch is None:
            continue
        mission_patch.status = "verified"
        mission_patch.updated_at = datetime.now(timezone.utc)
        # Return linked agents to monitoring so their status reflects the
        # verified outcome instead of the last approval-era message.
        agent_rows = await session.execute(select(AgentStatus).where(AgentStatus.linked_mission_patch_id == patch_id))
        for agent_row in agent_rows.scalars().all():
            agent_row.status = "monitoring"
            agent_row.phase = "monitor"
            agent_row.severity = "INFO"
            agent_row.message = (
                "Mission patch verified; monitoring for new findings."
                if agent_row.agent == "commander_agent"
                else "Related controls verified; monitoring baseline."
            )
            agent_row.linked_mission_patch_id = None
            agent_row.updated_by = "orbitops-executor"
            agent_row.updated_at = datetime.now(timezone.utc)
        if mission_patch.incident_id:
            incident = await session.get(Incident, mission_patch.incident_id)
            if incident is not None:
                incident.status = "resolved"
                incident.updated_at = datetime.now(timezone.utc)
                if incident.finding_ids:
                    findings_result = await session.execute(
                        select(AgentFinding).where(AgentFinding.id.in_(incident.finding_ids))
                    )
                    for finding in findings_result.scalars().all():
                        if finding.status == "open":
                            finding.status = "resolved"
        await state_writer(
            session,
            {
                "active_mission_patch": {
                    "id": patch_id,
                    "status": "verified",
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                },
                "training": {"status": "running_verified"},
            },
            updated_by="orbitops-executor",
            reason="verification.completed",
        )
        outbox_keys.extend(
            await _enqueue_event(
                session,
                outbox_enqueuer,
                StreamName.ui_events.value,
                "verification.completed",
                {"mission_patch_id": patch_id, "status": "verified"},
                f"outbox:{patch_id}:verification.completed",
            )
        )
    return outbox_keys


async def _enqueue_event(session, outbox_enqueuer, stream: str, event_type: str, payload: dict, key: str) -> list[str]:
    await outbox_enqueuer(
        session,
        stream=stream,
        event_type=event_type,
        payload=payload,
        idempotency_key=key,
    )
    return [key]


async def run_forever() -> None:
    await wait_for_database_ready()
    await wait_for_redis_ready()
    async with get_redis() as redis:
        try:
            await redis.xgroup_create(StreamName.command_requests.value, "executor", id="0", mkstream=True)
        except Exception as exc:  # noqa: BLE001
            if "BUSYGROUP" not in str(exc):
                raise
    while True:
        async with get_redis() as redis:
            messages = await redis.xreadgroup(
                "executor",
                "orbitops-executor-1",
                {StreamName.command_requests.value: ">"},
                count=1,
                block=1000,
            )
        if not messages:
            await asyncio.sleep(0.25)
            continue
        _stream_name, stream_messages = messages[0]
        message_id, _fields = stream_messages[0]
        await process_command_request_message(_fields, message_id)


async def process_command_request_message(
    fields: dict[str, Any],
    message_id: str,
    *,
    executor=execute_queued_commands_once,
    acknowledger=None,
) -> bool:
    mission_patch_id = parse_command_request(fields=fields)
    if mission_patch_id is None:
        return False
    await executor(mission_patch_id=mission_patch_id)
    if acknowledger is None:
        async with get_redis() as redis:
            await redis.xack(StreamName.command_requests.value, "executor", message_id)
    else:
        await acknowledger(message_id)
    return True


def parse_command_request(fields: dict[str, Any]) -> str | None:
    payload_value = fields.get("payload") or fields.get(b"payload")
    if payload_value is None:
        return None
    if isinstance(payload_value, bytes):
        payload_value = payload_value.decode("utf-8")
    if isinstance(payload_value, str):
        try:
            payload = json.loads(payload_value)
        except json.JSONDecodeError:
            return None
    elif isinstance(payload_value, dict):
        payload = payload_value
    else:
        return None
    if "payload" in payload and isinstance(payload["payload"], dict):
        payload = payload["payload"]
    mission_patch_id = payload.get("mission_patch_id")
    return mission_patch_id if isinstance(mission_patch_id, str) and mission_patch_id else None


if __name__ == "__main__":
    asyncio.run(run_forever())
