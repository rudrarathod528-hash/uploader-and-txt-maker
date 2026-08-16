from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def normalize_database_url(url: str) -> str:
    """Convert Railway's PostgreSQL URL to SQLAlchemy's asyncpg URL."""
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    return url


def create_database_engine(database_url: str) -> AsyncEngine:
    options: dict[str, Any] = {"pool_pre_ping": True}
    normalized_url = normalize_database_url(database_url)
    if not normalized_url.startswith("sqlite"):
        options.update(pool_recycle=300, pool_size=10, max_overflow=20)
    return create_async_engine(normalized_url, **options)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] = (
        request.app.state.db_session_factory
    )
    async with session_factory() as session:
        yield session
