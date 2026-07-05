from __future__ import annotations

import subprocess
from types import SimpleNamespace

from app.constants import DEMO_SCENARIO_RUN_ID
from app.services import local_gpu_telemetry
from app.services.local_gpu_telemetry import build_local_gpu_event, gpu_world_state_patch, parse_nvidia_smi_csv, read_nvidia_smi_snapshot


def test_parse_nvidia_smi_csv_sample() -> None:
    sample = "NVIDIA GeForce RTX 4070 Laptop GPU, 5, 14, 2516, 8188, 53, 3.52, [N/A]"

    snapshot = parse_nvidia_smi_csv(sample, node_id="node-local", asset_id="gpu-local-0")

    assert snapshot == {
        "source": "local_pc",
        "provider": "nvidia-smi",
        "node_id": "node-local",
        "asset_id": "gpu-local-0",
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


def test_parse_nvidia_smi_csv_invalid_output_returns_none() -> None:
    assert parse_nvidia_smi_csv("", node_id="node-local", asset_id="gpu-local-0") is None
    assert parse_nvidia_smi_csv("too, few, fields", node_id="node-local", asset_id="gpu-local-0") is None
    assert parse_nvidia_smi_csv(",,", node_id="node-local", asset_id="gpu-local-0") is None


def test_read_nvidia_smi_snapshot_returns_none_when_nvidia_smi_unavailable(monkeypatch) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("missing binary")

    monkeypatch.setattr(local_gpu_telemetry.subprocess, "run", fake_run)

    assert read_nvidia_smi_snapshot(node_id="node-local", asset_id="gpu-local-0") is None


def test_read_nvidia_smi_snapshot_returns_none_on_non_zero_exit(monkeypatch) -> None:
    def fake_run(*_args: object, **_kwargs: object):
        return SimpleNamespace(returncode=1, stdout="NVIDIA GeForce RTX 4070 Laptop GPU, 5, 14, 2516, 8188, 53, 3.52, [N/A]")

    monkeypatch.setattr(local_gpu_telemetry.subprocess, "run", fake_run)

    assert (
        read_nvidia_smi_snapshot(node_id="node-local", asset_id="gpu-local-0")
        is None
    )


def test_read_nvidia_smi_snapshot_returns_none_on_timeout(monkeypatch) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=2.0)

    monkeypatch.setattr(local_gpu_telemetry.subprocess, "run", fake_run)

    assert read_nvidia_smi_snapshot(node_id="node-local", asset_id="gpu-local-0") is None


def test_gpu_world_state_patch_shape() -> None:
    sample = parse_nvidia_smi_csv(
        "NVIDIA GeForce RTX 4070 Laptop GPU, 5, 14, 2516, 8188, 53, 3.52, [N/A]",
        node_id="node-local",
        asset_id="gpu-local-0",
    )
    assert sample is not None

    patch = gpu_world_state_patch(sample)

    assert "local_gpu" in patch
    assert "node_overrides" in patch
    assert "nodes" not in patch
    assert patch["local_gpu"]["node-local"]["read_only"] is True
    assert patch["node_overrides"]["node-local"]["read_only"] is True
    assert patch["node_overrides"]["node-local"]["status"] == "real_gpu_live"
    assert patch["node_overrides"]["node-local"]["gpu_util"] == 5
    assert patch["node_overrides"]["node-local"]["temp_c"] == 53


def test_build_local_gpu_event_shape() -> None:
    sample = parse_nvidia_smi_csv(
        "NVIDIA GeForce RTX 4070 Laptop GPU, 5, 14, 2516, 8188, 53, 3.52, [N/A]",
        node_id="node-local",
        asset_id="gpu-local-0",
    )
    assert sample is not None
    event = build_local_gpu_event(sample, world_state_version=11)

    assert event["type"] == "local_gpu.telemetry"
    assert event["event_type"] == "local_gpu.telemetry"
    assert event["scenario_run_id"] == DEMO_SCENARIO_RUN_ID
    assert event["asset_id"] == "gpu-local-0"
    assert event["severity"] == "INFO"
    assert event["world_state_version"] == 11
    assert event["payload"] == sample
