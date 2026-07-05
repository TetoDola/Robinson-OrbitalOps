from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

from pydantic import BaseModel


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "orbitops.sqlite3"
ALLOWED_TABLES = {
    "telemetry_snapshots",
    "agent_findings",
    "incidents",
    "mission_patches",
    "approval_events",
}


class OrbitOpsDatabase:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS telemetry_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    mission_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mission_patches (
                    patch_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approval_events (
                    event_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    patch_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )

    def reset_demo(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                DELETE FROM telemetry_snapshots;
                DELETE FROM agent_findings;
                DELETE FROM incidents;
                DELETE FROM mission_patches;
                DELETE FROM approval_events;
                """
            )

    def insert_model(self, table: str, model: BaseModel, columns: dict[str, Any]) -> None:
        if table not in ALLOWED_TABLES:
            raise ValueError(f"Unsupported table {table}")
        payload = model.model_dump(mode="json")
        row = {**columns, "payload": json.dumps(payload)}
        names = ", ".join(row)
        placeholders = ", ".join("?" for _ in row)
        values = list(row.values())
        with self._lock, self._connect() as conn:
            conn.execute(f"INSERT OR REPLACE INTO {table} ({names}) VALUES ({placeholders})", values)

    def latest_payload(self, table: str, order_column: str = "id") -> dict[str, Any] | None:
        if table not in ALLOWED_TABLES:
            raise ValueError(f"Unsupported table {table}")
        with self._lock, self._connect() as conn:
            row = conn.execute(
                f"SELECT payload FROM {table} ORDER BY {order_column} DESC LIMIT 1"
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_payloads(self, table: str, limit: int = 100, order_column: str = "id") -> list[dict[str, Any]]:
        if table not in ALLOWED_TABLES:
            raise ValueError(f"Unsupported table {table}")
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT payload FROM {table} ORDER BY {order_column} DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def list_payloads_ascending(self, table: str, limit: int = 100, order_column: str = "id") -> list[dict[str, Any]]:
        if table not in ALLOWED_TABLES:
            raise ValueError(f"Unsupported table {table}")
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT payload
                FROM (
                    SELECT {order_column}, payload
                    FROM {table}
                    ORDER BY {order_column} DESC
                    LIMIT ?
                )
                ORDER BY {order_column} ASC
                """,
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]
