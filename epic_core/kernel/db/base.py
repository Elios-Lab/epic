"""SQLAlchemy declarative base and async engine helpers."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    pass


def create_engine(database_url: str) -> AsyncEngine:
    kwargs = {}
    if database_url.startswith("sqlite") and ":memory:" not in database_url:
        # File-based SQLite: open/close a connection per checkout instead of
        # pooling. aiosqlite connections are bound to the event loop that
        # created them, so pooled connections leak (and warn) when sessions
        # run across multiple loops — as the test suite does. Opening a local
        # file per checkout is cheap; PostgreSQL keeps normal pooling.
        kwargs["poolclass"] = NullPool
    return create_async_engine(database_url, **kwargs)


async def create_all_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

