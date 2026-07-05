"""Local NVIDIA GPU telemetry extraction."""

from __future__ import annotations

import csv
import subprocess
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from app.constants import DEMO_SCENARIO_RUN_ID


_NVIDIA_QUERY_FIELDS = ",".join(
    [
        "name",
        "utilization.gpu",
        "utilization.memory",
        "memory.used",
        "memory.total",
        "temperature.gpu",
        "power.draw",
        "power.limit",
    ]
)


def _parse_scalar_numeric(value: str | None) -> int | float | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    upper = normalized.upper()
    if upper in {"N/A", "[N/A]"}:
        return None
    try:
        parsed = float(normalized)
    except (TypeError, ValueError):
        return None
    if parsed.is_integer():
        return int(parsed)
    return parsed


def parse_nvidia_smi_csv(output: str, *, node_id: str, asset_id: str) -> dict | None:
    """Parse a single-row nvidia-smi CSV line into a telemetry snapshot."""
    if not output:
        return None

    rows = [row for row in csv.reader(StringIO(output)) if row and any(cell.strip() for cell in row)]
    if not rows:
        return None

    row = rows[0]
    if len(row) != 8:
        return None

    name = row[0].strip() or None
    if name is None:
        return None

    return {
        "source": "local_pc",
        "provider": "nvidia-smi",
        "node_id": node_id,
        "asset_id": asset_id,
        "name": name,
        "gpu_util": _parse_scalar_numeric(row[1]),
        "memory_util": _parse_scalar_numeric(row[2]),
        "vram_used_mb": _parse_scalar_numeric(row[3]),
        "vram_total_mb": _parse_scalar_numeric(row[4]),
        "temp_c": _parse_scalar_numeric(row[5]),
        "power_w": _parse_scalar_numeric(row[6]),
        "power_limit_w": _parse_scalar_numeric(row[7]),
        "read_only": True,
    }


def read_nvidia_smi_snapshot(*, node_id: str, asset_id: str, timeout_seconds: float = 2.0) -> dict | None:
    """Read a single local GPU snapshot from nvidia-smi."""
    command = [
        "nvidia-smi",
        f"--query-gpu={_NVIDIA_QUERY_FIELDS}",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode != 0:
        return None

    return parse_nvidia_smi_csv(result.stdout, node_id=node_id, asset_id=asset_id)


def gpu_world_state_patch(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build a world-state patch for local GPU telemetry.

    Must keep datacenter `nodes` list untouched; this patch therefore only uses
    top-level dict merges with dedicated local/override namespaces.
    """
    node_id = str(snapshot.get("node_id", ""))
    local_gpu = {
        "source": snapshot.get("source"),
        "provider": snapshot.get("provider"),
        "asset_id": snapshot.get("asset_id"),
        "name": snapshot.get("name"),
        "gpu_util": snapshot.get("gpu_util"),
        "memory_util": snapshot.get("memory_util"),
        "vram_used_mb": snapshot.get("vram_used_mb"),
        "vram_total_mb": snapshot.get("vram_total_mb"),
        "temp_c": snapshot.get("temp_c"),
        "power_w": snapshot.get("power_w"),
        "power_limit_w": snapshot.get("power_limit_w"),
        "read_only": snapshot.get("read_only", True),
    }
    return {
        "local_gpu": {node_id: local_gpu},
        "node_overrides": {
            node_id: {
                "status": "real_gpu_live",
                "source": snapshot.get("source"),
                "provider": snapshot.get("provider"),
                "asset_id": snapshot.get("asset_id"),
                "gpu_util": snapshot.get("gpu_util"),
                "memory_util": snapshot.get("memory_util"),
                "vram_used_mb": snapshot.get("vram_used_mb"),
                "vram_total_mb": snapshot.get("vram_total_mb"),
                "temp_c": snapshot.get("temp_c"),
                "power_w": snapshot.get("power_w"),
                "power_limit_w": snapshot.get("power_limit_w"),
                "read_only": True,
            }
        },
    }


def build_local_gpu_event(snapshot: dict[str, Any], *, world_state_version: int | None = None) -> dict[str, Any]:
    """Create a TelemetryEvent payload for local GPU telemetry."""
    event: dict[str, Any] = {
        "type": "local_gpu.telemetry",
        "event_type": "local_gpu.telemetry",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenario_run_id": DEMO_SCENARIO_RUN_ID,
        "asset_id": snapshot.get("asset_id"),
        "severity": "INFO",
        "payload": snapshot,
    }
    if world_state_version is not None:
        event["world_state_version"] = world_state_version
    return event
