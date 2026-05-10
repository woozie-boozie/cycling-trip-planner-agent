"""FastAPI dependency providers.

Centralized so:
  - Tests can override via `app.dependency_overrides[get_session_store] = ...`
  - Phase 1.12 / 2D Postgres swaps are one-line changes here, nothing else changes.

Two stores wired here:
  - SessionStore — conversation state (Phase 1.4 in-memory; Phase 1.12b → Postgres)
  - ProfileStore — cyclist profile (Phase 2D Postgres-backed by default,
                                    falls back to SQLite engine for tests)
"""

from __future__ import annotations

import os
from functools import lru_cache

from anthropic import AsyncAnthropic

from src.agent.config import get_settings
from src.sessions import (
    InMemorySessionStore,
    PostgresProfileStore,
    PostgresSessionStore,
    ProfileStore,
    SessionStore,
)


def _make_session_store() -> SessionStore:
    """Pick the right SessionStore for the environment.

    Postgres when `DATABASE_URL` is set (Cloud Run, local dev with .env),
    InMemory otherwise. Tests don't set `DATABASE_URL`, and the test
    fixture provisions its own SQLite engine via `set_engine`, so the
    in-memory store remains the safe default for tests.

    Why env-driven and not a config flag: Cloud Run sets `DATABASE_URL`
    automatically when we --update-env-vars at deploy. One env var, one
    decision point, zero code changes between environments.
    """
    if os.getenv("DATABASE_URL"):
        return PostgresSessionStore()
    return InMemorySessionStore()


# Process-singletons. ProfileStore already routed through Postgres (or
# SQLite in tests via fixture). SessionStore now mirrors that pattern.
_session_store: SessionStore = _make_session_store()
_profile_store: ProfileStore = PostgresProfileStore()


def get_session_store() -> SessionStore:
    return _session_store


def get_profile_store() -> ProfileStore:
    return _profile_store


@lru_cache(maxsize=1)
def get_anthropic_client() -> AsyncAnthropic:
    """Cached so we share an httpx connection pool across requests."""
    settings = get_settings()
    return AsyncAnthropic(api_key=settings.anthropic_api_key)
