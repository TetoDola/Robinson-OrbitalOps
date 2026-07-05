"""Command routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Command
from app.db.session import get_session

router = APIRouter(tags=["commands"])


@router.get("/commands")
async def list_commands(session: AsyncSession = Depends(get_session)) -> dict:
    result = await session.execute(select(Command).order_by(Command.created_at.desc()))
    return {"commands": [_command_payload(row) for row in result.scalars().all()]}


@router.get("/commands/{command_id}")
async def get_command(command_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    command = await session.get(Command, command_id)
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found.")
    return {"command": _command_payload(command)}


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
