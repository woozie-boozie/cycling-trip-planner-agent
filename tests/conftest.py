"""Shared pytest fixtures.

The big one is `seeded_db` — provisions a SQLite in-memory database, runs
the seed script against it, and yields. Every tool test that hits the DB
uses this fixture so we never depend on Postgres being available in CI.

Same SQLModel schema runs against both Postgres (production) and SQLite
(tests). For the queries we use, behaviour is identical.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio

from src.db import create_async_engine_for_url, init_db, set_engine
from src.db.engine import DEFAULT_TEST_URL


@pytest_asyncio.fixture
async def seeded_db() -> AsyncIterator[None]:
    """Fresh SQLite + tables + seeded tool data for every test that needs DB."""
    # Use a file-based SQLite per test instead of pure :memory: so async
    # connections see the same tables (in-memory mode is per-connection).
    engine = create_async_engine_for_url(DEFAULT_TEST_URL)
    set_engine(engine)
    await init_db()

    # Run the seed script
    from src.db.seed import (
        seed_accommodations,
        seed_elevation,
        seed_routes,
        seed_weather,
    )

    await seed_routes()
    await seed_accommodations()
    await seed_weather()
    await seed_elevation()

    yield

    await engine.dispose()


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """Session-scoped loop so async fixtures share state cleanly."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
