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


@pytest.fixture(autouse=True, scope="session")
def _disable_real_apis_in_tests() -> Iterator[None]:
    """Force tests off the real-API code paths.

    Without this, a developer's local ``.env`` (with ``USE_REAL_ROUTES=true``
    or ``USE_REAL_WEATHER=true``) leaks into the test process and causes
    cross-event-loop httpx singletons to crash. Tests should be hermetic —
    real HTTP calls belong in the eval suite, not unit tests.
    """
    import os

    saved = {k: os.environ.get(k) for k in ("USE_REAL_ROUTES", "USE_REAL_WEATHER")}
    for k in ("USE_REAL_ROUTES", "USE_REAL_WEATHER"):
        os.environ[k] = ""
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


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
