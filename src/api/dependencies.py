"""FastAPI dependency providers.

Centralized so:
  - Tests can override via `app.dependency_overrides[get_session_store] = ...`
  - Phase 1.12 (Postgres) is a one-line swap — replace `_session_store` here
    and nothing else changes.
"""

from __future__ import annotations

from functools import lru_cache

from anthropic import AsyncAnthropic

from src.agent.config import get_settings
from src.sessions import InMemorySessionStore, SessionStore

# Process-singleton for v1. When Postgres lands, this becomes a connection pool.
_session_store: SessionStore = InMemorySessionStore()


def get_session_store() -> SessionStore:
    return _session_store


@lru_cache(maxsize=1)
def get_anthropic_client() -> AsyncAnthropic:
    """Cached so we share an httpx connection pool across requests."""
    settings = get_settings()
    return AsyncAnthropic(api_key=settings.anthropic_api_key)
