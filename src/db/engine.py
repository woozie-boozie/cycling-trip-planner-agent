"""Async SQLAlchemy engine + session factory.

The engine is process-singleton and lazy. Tests can replace it via
`set_engine(...)` to point at SQLite in-memory.

Connection URL conventions:
  - Production: `postgresql+asyncpg://user:pass@host/db?ssl=require`
  - Tests:      `sqlite+aiosqlite:///:memory:`
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

# Load .env on first import so DATABASE_URL is available everywhere — the
# seed script, the FastAPI app, the smoke test, etc. pydantic-settings
# already reads .env for the agent config but doesn't push to os.environ,
# so we'd otherwise lose DATABASE_URL for callers that use os.getenv.
load_dotenv()

DEFAULT_TEST_URL = "sqlite+aiosqlite:///:memory:"

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _resolve_url() -> str:
    """Pick the engine URL.

    Order of precedence:
      1. DATABASE_URL env var
      2. SQLite in-memory fallback (so tests work without configuration)

    Neon-specific normalizations:
      - `postgresql://` → `postgresql+asyncpg://` so SQLAlchemy picks the async driver
      - `sslmode=require` → `ssl=require` (asyncpg's keyword)
      - drop `channel_binding=require` (asyncpg rejects this kwarg —
        SCRAM channel binding is enabled implicitly when SSL is used)
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        return DEFAULT_TEST_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    url = url.replace("sslmode=require", "ssl=require")
    # Strip Neon's channel_binding parameter — asyncpg doesn't recognize it.
    for variant in ("&channel_binding=require", "?channel_binding=require"):
        url = url.replace(variant, "")
    # If we just stripped a leading "?channel_binding=require", make sure
    # the next param starts with "?" not "&".
    url = url.replace("?&", "?")
    return url


def create_async_engine_for_url(url: str) -> AsyncEngine:
    """Build a fresh engine. Used by tests + the lazy default.

    SQLite in-memory needs special handling: a shared `StaticPool` so every
    session reuses the same connection (otherwise each connection gets its
    own empty DB). Postgres uses the default async pool.
    """
    if "sqlite" in url and ":memory:" in url:
        return create_async_engine(
            url,
            echo=False,
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_async_engine(
        url,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )


def get_engine() -> AsyncEngine:
    """Return the process-wide engine, creating one on first call."""
    global _engine, _session_factory
    if _engine is None:
        _engine = create_async_engine_for_url(_resolve_url())
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def set_engine(engine: AsyncEngine) -> None:
    """Tests use this to inject a SQLite engine. Resets the session factory."""
    global _engine, _session_factory
    _engine = engine
    _session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Async context manager yielding a session bound to the current engine."""
    if _session_factory is None:
        get_engine()  # initialize lazily
    assert _session_factory is not None
    async with _session_factory() as session:
        yield session


async def init_db() -> None:
    """Create all tables. Idempotent — safe to call on every startup.

    For SQLite tests this is the only way to materialize the schema.
    For Postgres it's how we bootstrap a fresh Neon project (no Alembic
    yet — case study scope).
    """
    # Importing models registers their metadata with SQLModel.
    from src.db import models  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
