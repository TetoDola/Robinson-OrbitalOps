"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db.session import engine
from app.services.redis_client import close_redis
from app.routers.agents import router as agents_router
from app.routers.chat import router as chat_router
from app.routers.commands import router as commands_router
from app.routers.health import router as health_router
from app.routers.incidents import router as incidents_router
from app.routers.mission_patches import router as mission_patches_router
from app.routers.radiation import router as radiation_router
from app.routers.simulator import router as simulator_router
from app.routers.websocket import router as websocket_router
from app.routers.world_state import router as world_state_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(world_state_router, prefix=settings.api_prefix)
app.include_router(agents_router, prefix=settings.api_prefix)
app.include_router(chat_router, prefix=settings.api_prefix)
app.include_router(incidents_router, prefix=settings.api_prefix)
app.include_router(mission_patches_router, prefix=settings.api_prefix)
app.include_router(commands_router, prefix=settings.api_prefix)
app.include_router(radiation_router, prefix=settings.api_prefix)
app.include_router(simulator_router, prefix=settings.api_prefix)
app.include_router(websocket_router, prefix=settings.api_prefix)
