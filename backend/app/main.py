"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db.session import engine
from app.services.bootstrap import startup as bootstrap_startup
from app.services.redis_client import close_redis
from app.routers.agents import router as agents_router
from app.routers.health import router as health_router
from app.routers.websocket import router as websocket_router
from app.routers.world_state import router as world_state_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await bootstrap_startup()
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(world_state_router, prefix=settings.api_prefix)
app.include_router(agents_router, prefix=settings.api_prefix)
app.include_router(websocket_router, prefix=settings.api_prefix)
