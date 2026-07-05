from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from app.db.models import Command, MissionPatch, OutboxEvent
from app.services.command_executor import (
    execute_commands_in_session,
    execute_queued_commands_once,
    parse_command_request,
    process_command_request_message,
)
from app.services.outbox import publish_outbox_events_by_keys


class _Result:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class _FakeExecutorSession:
    def __init__(self, patches: dict[str, MissionPatch], commands: list[Command]):
        self.patches = patches
        self.commands = commands
        self.commits = 0
        self.state_patches: list[dict] = []
        self.outbox_events: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, statement):
        params = statement.compile().params
        mission_patch_id = next((value for key, value in params.items() if key.startswith("mission_patch_id")), None)
        commands = [command for command in self.commands if command.status == "queued"]
        if mission_patch_id is not None:
            commands = [command for command in commands if command.mission_patch_id == mission_patch_id]
        return _Result(commands)

    async def get(self, model, key):
        if model is MissionPatch:
            return self.patches.get(key)
        return None

    async def commit(self):
        self.commits += 1


class _FakeOutboxSession:
    def __init__(self, events: list[OutboxEvent]):
        self.events = events
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, _statement):
        return _Result(self.events)

    async def commit(self):
        self.commits += 1


def _patch(patch_id: str) -> MissionPatch:
    return MissionPatch(
        id=patch_id,
        scenario_run_id="phase-1-run",
        incident_id=f"incident-{patch_id}",
        severity="RED",
        status="approved",
        summary="Demo patch.",
        evidence=[],
        actions=[],
        rollback_plan={},
        approval_required=True,
    )


def _command(command_id: str, patch_id: str, action: dict[str, Any]) -> Command:
    return Command(
        id=command_id,
        scenario_run_id="phase-1-run",
        mission_patch_id=patch_id,
        action_type=action["type"],
        target_asset_id=action.get("node_id") or action.get("checkpoint_id") or action.get("job_id"),
        status="queued",
        input=action,
        result={},
        idempotency_key=f"command:{command_id}",
    )


async def _fake_state_writer(session, state_patch, *, updated_by, reason):
    session.state_patches.append({"state_patch": state_patch, "updated_by": updated_by, "reason": reason})


async def _fake_outbox_enqueuer(session, *, stream, event_type, payload, idempotency_key):
    session.outbox_events.append(
        {
            "stream": stream,
            "event_type": event_type,
            "payload": payload,
            "idempotency_key": idempotency_key,
        }
    )


def test_executor_lifecycle_updates_commands_patch_world_state_and_outbox() -> None:
    patch = _patch("patch-042")
    commands = [
        _command("command-1", patch.id, {"type": "mark_checkpoint_suspect", "checkpoint_id": "ckpt-184900"}),
        _command(
            "command-2",
            patch.id,
            {"type": "run_health_check", "asset_id": "node-a", "check_suite": "distributed_training"},
        ),
    ]
    session = _FakeExecutorSession({patch.id: patch}, commands)

    outbox_keys = asyncio.run(
        execute_commands_in_session(
            session,
            commands,
            state_writer=_fake_state_writer,
            outbox_enqueuer=_fake_outbox_enqueuer,
        )
    )

    assert patch.status == "verified"
    assert all(command.status == "succeeded" for command in commands)
    assert all(command.result["verified"] is True for command in commands)
    assert any(item["state_patch"].get("active_mission_patch", {}).get("status") == "verified" for item in session.state_patches)
    assert any(item["state_patch"].get("training", {}).get("latest_checkpoint_status") == "suspect" for item in session.state_patches)

    event_types_by_stream = {(event["stream"], event["event_type"]) for event in session.outbox_events}
    assert ("ui:events", "mission_patch.executing") in event_types_by_stream
    assert ("ui:events", "command.started") in event_types_by_stream
    assert ("ui:events", "command.succeeded") in event_types_by_stream
    assert ("command:results", "command.succeeded") in event_types_by_stream
    assert ("ui:events", "verification.completed") in event_types_by_stream
    assert outbox_keys == [event["idempotency_key"] for event in session.outbox_events]


def test_execute_queued_commands_once_runs_only_requested_patch_commands() -> None:
    patch_a = _patch("patch-a")
    patch_b = _patch("patch-b")
    command_a = _command("command-a", patch_a.id, {"type": "run_health_check", "asset_id": "node-a", "check_suite": "distributed_training"})
    command_b = _command("command-b", patch_b.id, {"type": "run_health_check", "asset_id": "node-b", "check_suite": "distributed_training"})
    session = _FakeExecutorSession({patch_a.id: patch_a, patch_b.id: patch_b}, [command_a, command_b])
    published_keys = []

    @asynccontextmanager
    async def session_factory():
        yield session

    async def fake_publisher(keys):
        published_keys.extend(keys)

    count = asyncio.run(
        execute_queued_commands_once(
            mission_patch_id=patch_a.id,
            session_factory=session_factory,
            state_writer=_fake_state_writer,
            outbox_enqueuer=_fake_outbox_enqueuer,
            outbox_publisher=fake_publisher,
        )
    )

    assert count == 1
    assert command_a.status == "succeeded"
    assert command_b.status == "queued"
    assert patch_a.status == "verified"
    assert patch_b.status == "approved"
    assert session.commits == 1
    assert published_keys == [event["idempotency_key"] for event in session.outbox_events]


def test_process_command_request_acknowledges_after_scoped_execution() -> None:
    calls = []

    async def fake_executor(*, mission_patch_id):
        calls.append(("execute", mission_patch_id))

    async def fake_acknowledger(message_id):
        calls.append(("ack", message_id))

    processed = asyncio.run(
        process_command_request_message(
            {"payload": '{"type":"command.batch_created","payload":{"mission_patch_id":"patch-042"}}'},
            "message-1",
            executor=fake_executor,
            acknowledger=fake_acknowledger,
        )
    )

    assert processed is True
    assert calls == [("execute", "patch-042"), ("ack", "message-1")]


def test_parse_command_request_extracts_mission_patch_id_from_stream_payload() -> None:
    assert parse_command_request({"payload": '{"mission_patch_id":"patch-042","command_count":3}'}) == "patch-042"
    assert parse_command_request({"payload": b'{"mission_patch_id":"patch-042"}'}) == "patch-042"
    assert parse_command_request({"payload": '{"type":"command.batch_created","payload":{"mission_patch_id":"patch-042"}}'}) == "patch-042"
    assert parse_command_request({b"payload": b'{"type":"command.batch_created","payload":{"mission_patch_id":"patch-042"}}'}) == "patch-042"
    assert parse_command_request({"payload": '{"command_count":3}'}) is None
    assert parse_command_request({"payload": "not-json"}) is None


def test_outbox_publisher_preserves_requested_key_order() -> None:
    now = datetime.now(timezone.utc)
    events = [
        OutboxEvent(id="event-2", stream="ui:events", event_type="second", payload={}, status="pending", idempotency_key="key-2", created_at=now),
        OutboxEvent(id="event-1", stream="ui:events", event_type="first", payload={}, status="pending", idempotency_key="key-1", created_at=now),
    ]
    session = _FakeOutboxSession(events)
    published = []

    @asynccontextmanager
    async def session_factory():
        yield session

    async def fake_publisher(_stream, event):
        published.append(event["type"])

    count = asyncio.run(
        publish_outbox_events_by_keys(
            ["key-1", "key-2"],
            session_factory=session_factory,
            publisher=fake_publisher,
        )
    )

    assert count == 2
    assert published == ["first", "second"]
    assert [event.status for event in events] == ["published", "published"]
    assert session.commits == 1
