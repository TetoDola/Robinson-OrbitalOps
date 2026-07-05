"""Transactional outbox helpers for Redis stream publication."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OutboxEvent
from app.db.session import session_context
from app.services.event_bus import publish_stream_event


async def enqueue_outbox_event(
    session: AsyncSession,
    *,
    stream: str,
    event_type: str,
    payload: dict,
    idempotency_key: str,
) -> OutboxEvent | None:
    result = await session.execute(select(OutboxEvent).where(OutboxEvent.idempotency_key == idempotency_key))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return None

    event = OutboxEvent(
        stream=stream,
        event_type=event_type,
        payload=payload,
        status="pending",
        idempotency_key=idempotency_key,
    )
    session.add(event)
    return event


async def publish_outbox_events_by_keys(
    idempotency_keys: list[str],
    *,
    session_factory=session_context,
    publisher=publish_stream_event,
) -> int:
    if not idempotency_keys:
        return 0

    published = 0
    async with session_factory() as session:
        result = await session.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.idempotency_key.in_(idempotency_keys),
                OutboxEvent.status == "pending",
            )
        )
        events_by_key = {event.idempotency_key: event for event in result.scalars().all()}
        for key in idempotency_keys:
            event = events_by_key.get(key)
            if event is None:
                continue
            await publisher(
                event.stream,
                {
                    "type": event.event_type,
                    "timestamp": event.created_at.isoformat(),
                    "payload": event.payload,
                },
            )
            event.status = "published"
            event.published_at = datetime.now(timezone.utc)
            published += 1
        await session.commit()
    return published
