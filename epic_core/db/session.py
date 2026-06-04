"""Async database session factory and dependency."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from epic_core.db.base import create_engine

_engine: AsyncEngine | None = None
AsyncSessionFactory: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str) -> None:
    global _engine, AsyncSessionFactory
    if _engine is None:
        _engine = create_engine(database_url)
        AsyncSessionFactory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if AsyncSessionFactory is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")

    async with AsyncSessionFactory() as session:
        yield session
