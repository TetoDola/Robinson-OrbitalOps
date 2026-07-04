"""Async SQLAlchemy session and transaction helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionFactory = async_sessionmaker(bind=engine, expire_on_commit=False)


@asynccontextmanager
async def session_context() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionFactory() as session:
        yield session


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        yield session


async def ping_database() -> bool:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        return True
