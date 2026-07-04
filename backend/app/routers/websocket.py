"""WebSocket live updates."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.config import settings
from app.db.models import AgentStatus, WorldStateCurrent
from app.db.session import session_context

router = APIRouter()


async def _send_heartbeat(websocket: WebSocket, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await websocket.send_json(
            {
                "type": "heartbeat",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"status": "alive"},
            }
        )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.websocket_heartbeat_seconds)
        except asyncio.TimeoutError:
            continue


async def _send_seeded_snapshot(websocket: WebSocket) -> None:
    async with session_context() as session:
        world_stmt = select(WorldStateCurrent).where(WorldStateCurrent.id.is_(True))
        world_result = await session.execute(world_stmt)
        world_state = world_result.scalar_one_or_none()
        if world_state is not None:
            await websocket.send_json(
                {
                    "type": "world_state.updated",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "version": world_state.version,
                        "scenario_run_id": world_state.scenario_run_id,
                        "state": world_state.state,
                    },
                }
            )

        agent_stmt = select(AgentStatus).order_by(AgentStatus.agent.asc())
        agent_result = await session.execute(agent_stmt)
        for row in agent_result.scalars().all():
            await websocket.send_json(
                {
                    "type": "agent.status.updated",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "agent": row.agent,
                        "display_name": row.display_name,
                        "status": row.status,
                        "phase": row.phase,
                        "severity": row.severity,
                        "message": row.message,
                        "linked_mission_patch_id": row.linked_mission_patch_id,
                    },
                }
            )


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    await websocket.accept()
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(_send_heartbeat(websocket, stop_event))

    try:
        await _send_seeded_snapshot(websocket)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
