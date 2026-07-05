"""Startup helpers for safe boot on API and Compose."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import settings
from app.db.seed import seed_initial_data
from app.db.session import ping_database, session_context
from app.services.redis_client import ping_redis


async def wait_for_database_ready() -> None:
    attempts = settings.database_retry_attempts
    delay = settings.database_retry_delay_seconds
    for attempt in range(1, attempts + 1):
        try:
            if await ping_database():
                return
        except Exception:
            if attempt < attempts:
                await asyncio.sleep(delay)
                continue
    raise RuntimeError("Postgres did not become ready in time.")


async def wait_for_redis_ready() -> None:
    await ping_redis()


async def run_migrations() -> None:
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    await asyncio.to_thread(command.upgrade, cfg, "head")


async def seed_runtime_data() -> None:
    async with session_context() as session:
        await seed_initial_data(session)


async def startup() -> None:
    await wait_for_database_ready()
    await wait_for_redis_ready()
    await run_migrations()
    await seed_runtime_data()


def run_uvicorn() -> None:
    os.execv(
        sys.executable,
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", settings.api_host, "--port", str(settings.api_port)],
    )


async def main() -> None:
    await startup()
    run_uvicorn()


if __name__ == "__main__":
    asyncio.run(main())
