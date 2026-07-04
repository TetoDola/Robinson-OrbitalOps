"""Mock command executor for approved Phase 3 mission patches."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.constants import StreamName
from app.db.models import Command, MissionPatch
from app.db.session import session_context
from app.services.bootstrap import wait_for_database_ready, wait_for_redis_ready
from app.services.event_bus import publish_stream_event
from app.services.redis_client import get_redis
from app.services.world_state import write_world_state


def apply_action_to_state(action: dict) -> dict:
    action_type = action["type"]
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


async def execute_queued_commands_once() -> int:
    post_commit_events = []
    async with session_context() as session:
        result = await session.execute(
            select(Command).where(Command.status == "queued").order_by(Command.created_at.asc()).with_for_update(skip_locked=True)
        )
        commands = list(result.scalars().all())
        for command in commands:
            command.status = "running"
            post_commit_events.append(
                {
                    "stream": StreamName.ui_events.value,
                    "type": "command.started",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {"id": command.id, "action_type": command.action_type},
                }
            )
            patch = apply_action_to_state(command.input)
            if patch:
                await write_world_state(session, patch, updated_by="orbitops-executor", reason=command.action_type)
            command.status = "succeeded"
            command.result = {"verified": True, "message": f"{command.action_type} completed"}
            command.updated_at = datetime.now(timezone.utc)
            post_commit_events.append(
                {
                    "stream": StreamName.command_results.value,
                    "type": "command.succeeded",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {"id": command.id, "result": command.result},
                }
            )

        patch_ids = {command.mission_patch_id for command in commands}
        for patch_id in patch_ids:
            mission_patch = await session.get(MissionPatch, patch_id)
            if mission_patch is not None:
                mission_patch.status = "verified"
                mission_patch.updated_at = datetime.now(timezone.utc)
                post_commit_events.append(
                    {
                        "stream": StreamName.ui_events.value,
                        "type": "verification.completed",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "payload": {"mission_patch_id": patch_id, "status": "verified"},
                    }
                )
        await session.commit()

    for event in post_commit_events:
        stream = event.pop("stream")
        await publish_stream_event(stream, event)
    return len(commands)


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
        await execute_queued_commands_once()
        async with get_redis() as redis:
            await redis.xack(StreamName.command_requests.value, "executor", message_id)


if __name__ == "__main__":
    asyncio.run(run_forever())
