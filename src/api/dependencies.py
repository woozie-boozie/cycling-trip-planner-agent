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

from functools import lru_cache

from anthropic import AsyncAnthropic

from src.agent.config import get_settings
from src.sessions import (
    InMemorySessionStore,
    PostgresProfileStore,
    ProfileStore,
    SessionStore,
)

# Process-singleton for v1. When session-Postgres lands, this becomes a real
# PostgresSessionStore. ProfileStore already uses Postgres (or SQLite in tests).
_session_store: SessionStore = InMemorySessionStore()
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
