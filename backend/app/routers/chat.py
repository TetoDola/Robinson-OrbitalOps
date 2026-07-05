"""Operator chatbot routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentFinding, AgentStatus, Command, MissionPatch, WorldStateCurrent
from app.db.session import get_session
from app.schemas.chat import ChatContextSummary, ChatTurn, OperatorChatRequest, OperatorChatResponse
from app.services.operator_chat import build_operator_chat_reply

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=OperatorChatResponse)
async def operator_chat(
    request: OperatorChatRequest,
    session: AsyncSession = Depends(get_session),
) -> OperatorChatResponse:
    world_state_result = await session.execute(select(WorldStateCurrent).where(WorldStateCurrent.id.is_(True)))
    agents_result = await session.execute(select(AgentStatus).order_by(AgentStatus.agent.asc()))
    findings_result = await session.execute(select(AgentFinding).order_by(AgentFinding.created_at.desc()).limit(25))
    commands_result = await session.execute(select(Command).order_by(Command.created_at.desc()).limit(25))
    patch_result = await session.execute(
        select(MissionPatch)
        .where(MissionPatch.status.in_(["pending_approval", "approved", "executing"]))
        .order_by(MissionPatch.created_at.desc())
    )

    reply = await build_operator_chat_reply(
        message=request.message.strip(),
        history=request.history,
        world_state=world_state_result.scalar_one_or_none(),
        agents=list(agents_result.scalars().all()),
        findings=list(findings_result.scalars().all()),
        commands=list(commands_result.scalars().all()),
        mission_patch=patch_result.scalars().first(),
    )

    return OperatorChatResponse(
        message=ChatTurn(role="assistant", content=reply.content),
        source=reply.source,
        model=reply.model,
        context=ChatContextSummary(**reply.context_summary),
    )
