from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.constants import DEMO_BASELINE_WORLD_STATE, StreamName
from app.services.manual_simulation import _manual_injection_bucket
from app.simulator import telemetry_generator
from app.simulator.state_machine import build_simulated_state, build_telemetry_payload


def test_simulated_state_changes_orbit_without_creating_default_issue() -> None:
    tick_0 = build_simulated_state(0)
    tick_5 = build_simulated_state(5)

    assert tick_0["satellite"]["lat"] != tick_5["satellite"]["lat"]
    assert tick_0["satellite"]["lon"] != tick_5["satellite"]["lon"]
    assert tick_5["satellite"]["time_to_eclipse_min"] == 31
    assert tick_5["power"]["battery_percent"] == 62
    assert tick_5["thermal"]["highest_temp_c"] == 62
    assert tick_5["radiation"]["risk"] == "nominal"
    assert tick_5["training"]["latest_checkpoint_status"] == "trusted"
    assert all(node["temp_c"] < 80 for node in tick_5["nodes"] if "temp_c" in node)


def test_telemetry_payload_contains_phase2_domains() -> None:
    state = build_simulated_state(5)
    payload = build_telemetry_payload(state)

    assert payload["satellite"]["id"] == "orbital-dc-01"
    assert payload["power"]["battery_percent"] == 62
    assert payload["thermal"]["hotspot_node"] == "none"
    assert payload["thermal"]["highest_temp_c"] < 80
    assert payload["radiation"]["ecc_errors_last_5min"] == 12
    assert payload["downlink"]["capacity_gb"] == 180


def test_tick_zero_is_clean_demo_baseline() -> None:
    state = build_simulated_state(0)

    assert state == DEMO_BASELINE_WORLD_STATE


def test_vibration_manual_bucket_uses_attached_audio_id() -> None:
    timestamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    state = {
        "thermal": {
            "latest_visual_input": {
                "audio_id": "audio-evidence-1234567890",
                "received_at": timestamp.isoformat(),
            }
        }
    }

    assert _manual_injection_bucket("vibration-fault", state, timestamp) == "vibration-fault-audio-eviden"


def test_vibration_manual_bucket_ignores_stale_audio_id() -> None:
    timestamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    state = {
        "thermal": {
            "latest_visual_input": {
                "audio_id": "old-audio-evidence",
                "received_at": "2026-01-02T03:04:04+00:00",
            }
        }
    }

    assert _manual_injection_bucket("vibration-fault", state, timestamp) == "vibration-fault-1767323045000"


class _FakeWorldState:
    def __init__(self, version: int, state: dict) -> None:
        self.version = version
        self.state = state


class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.added = []

    def add(self, row) -> None:
        self.added.append(row)

    async def commit(self) -> None:
        self.commits += 1


class _SessionContext:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> None:
        return None


def test_run_simulator_tick_emits_local_gpu_telemetry_and_commits_once(monkeypatch) -> None:
    session = _FakeSession()
    world_state_version = 0
    world_state = {}
    written_patches = []

    def fake_session_context() -> _SessionContext:
        return _SessionContext(session)

    async def fake_write_world_state(_session, patch, *, updated_by: str, reason: str):
        written_patches.append((patch, updated_by, reason))
        nonlocal world_state, world_state_version
        merged_state = dict(world_state)
        merged_state.update(patch)
        world_state_version += 1
        world_state = merged_state
        return _FakeWorldState(world_state_version, world_state)

    def fake_read_snapshot(*, node_id: str, asset_id: str, timeout_seconds: float = 2.0):
        return {
            "source": "local_pc",
            "provider": "nvidia-smi",
            "node_id": node_id,
            "asset_id": asset_id,
            "name": "NVIDIA GeForce RTX 4070 Laptop GPU",
            "gpu_util": 5,
            "memory_util": 14,
            "vram_used_mb": 2516,
            "vram_total_mb": 8188,
            "temp_c": 53,
            "power_w": 3.52,
            "power_limit_w": None,
            "read_only": True,
        }

    published_events = []

    async def fake_publish(stream: str, event: dict) -> None:
        published_events.append((stream, event))

    monkeypatch.setattr("app.simulator.telemetry_generator.session_context", fake_session_context)
    monkeypatch.setattr("app.simulator.telemetry_generator.read_nvidia_smi_snapshot", fake_read_snapshot)
    monkeypatch.setattr("app.simulator.telemetry_generator.write_world_state", fake_write_world_state)
    monkeypatch.setattr("app.simulator.telemetry_generator.publish_stream_event", fake_publish)
    monkeypatch.setattr("app.simulator.telemetry_generator.settings.local_gpu_telemetry_enabled", True)

    result = asyncio.run(telemetry_generator.run_simulator_tick(0))

    telemetry_events = [event for stream, event in published_events if stream == StreamName.telemetry_events.value]
    ui_events = [event for stream, event in published_events if stream == StreamName.ui_events.value]

    assert result["world_state_version"] == 2
    assert session.commits == 1
    assert len(written_patches) == 2
    assert written_patches[1][1] == "robinson-local-gpu"
    assert written_patches[1][2] == "local_gpu_telemetry"
    assert "nodes" not in written_patches[1][0]
    assert "local_gpu" in written_patches[1][0]
    assert "node_overrides" in written_patches[1][0]
    assert telemetry_events[0]["event_type"] == "simulator.tick"
    assert telemetry_events[1]["event_type"] == "local_gpu.telemetry"
    assert any(event["type"] == "world_state.updated" for event in ui_events)
    assert any(event["type"] == "local_gpu.telemetry" for event in ui_events)
