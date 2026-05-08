"""Database layer.

Single source of truth for the app's storage. Currently:
  - Tool data (routes, accommodation, weather norms, elevation) lives here
    via SQLModel-defined tables
  - Sessions will move here in Phase 1.12b (PostgresSessionStore)

The engine is selected by env: `DATABASE_URL` chooses the backend.
  - Production: Neon Postgres via asyncpg (postgresql+asyncpg://...)
  - Tests: SQLite in-memory (sqlite+aiosqlite:///:memory:)
"""

from src.db.engine import (
    DEFAULT_TEST_URL,
    create_async_engine_for_url,
    get_async_session,
    get_engine,
    init_db,
    set_engine,
)

__all__ = [
    "DEFAULT_TEST_URL",
    "create_async_engine_for_url",
    "get_async_session",
    "get_engine",
    "init_db",
    "set_engine",
]
