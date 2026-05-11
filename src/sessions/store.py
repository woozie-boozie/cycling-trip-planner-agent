"""Session store — interface and in-memory implementation.

The Protocol defines the contract that a Postgres-backed implementation
satisfies. By committing to this shape, the in-memory ↔ Postgres swap is
one line in `src/api/dependencies.py` rather than a refactor.

Methods are async even for the in-memory case so the interface stays
identical when the real implementation becomes I/O-bound.

Concurrency model — optimistic locking:
  Concurrent ``put`` calls for the same ``session_id`` would silently lose
  data without a coordination primitive. We use **optimistic locking**:
  every ``ConversationState`` carries a ``version`` field that increments
  on each successful ``put``. The store's ``put`` raises ``SessionConflict``
  when the version it sees on disk doesn't match the version the caller
  loaded with — the loser of the race retries or surfaces a 409 to the
  user. The version lives in both the JSON blob (caller awareness) AND
  the DB column (SQL-level enforcement on Postgres). See
  ``PostgresSessionStore.put`` for the conditional-update mechanics.
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

from src.agent.state import ConversationState


class SessionConflict(RuntimeError):
    """Raised when a concurrent ``put`` lost the optimistic-locking race.

    Carriers (chat endpoint, agent loop) should surface this to the caller
    as HTTP 409 Conflict — the client can refetch the session and retry
    with the fresh state, or display "another request is in flight" to
    the user. Never swallow — silent retries can amplify the very
    concurrency the locking is preventing.
    """


@runtime_checkable
class SessionStore(Protocol):
    """The contract every session store must satisfy."""

    async def get(self, session_id: str) -> ConversationState | None:
        ...

    async def put(self, state: ConversationState) -> None:
        """Persist ``state`` and increment its version on success.

        Raises ``SessionConflict`` if the on-disk version doesn't match
        ``state.version`` (someone else wrote between get and put).
        """
        ...

    async def delete(self, session_id: str) -> bool:
        ...

    async def list_ids(self) -> list[str]:
        ...


class InMemorySessionStore:
    """Process-local dict. Sessions reset on server restart — acceptable
    when running a single Cloud Run instance or for tests.

    Thread/coroutine-safe via an asyncio.Lock guarding mutations. Honors
    the same optimistic-locking semantics as ``PostgresSessionStore`` so
    tests exercise the same code paths the production store does.
    """

    def __init__(self) -> None:
        self._data: dict[str, ConversationState] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str) -> ConversationState | None:
        # Deep-copy on read so two concurrent callers each get an isolated
        # ConversationState. Without this, both readers would mutate the
        # same dict entry and the version check would never fire — every
        # writer would see its own already-incremented version. Mirrors
        # what the Postgres store does naturally via Pydantic-from-JSON
        # round-trip on each get().
        existing = self._data.get(session_id)
        if existing is None:
            return None
        return existing.model_copy(deep=True)

    async def put(self, state: ConversationState) -> None:
        async with self._lock:
            existing = self._data.get(state.session_id)
            if existing is not None and existing.version != state.version:
                raise SessionConflict(
                    f"session {state.session_id!r} was modified concurrently "
                    f"(expected version {state.version}, found {existing.version})"
                )
            state.touch()
            state.version += 1
            # Store a deep copy so the caller can keep mutating their
            # ConversationState without leaking changes into the store.
            self._data[state.session_id] = state.model_copy(deep=True)

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            return self._data.pop(session_id, None) is not None

    async def list_ids(self) -> list[str]:
        return list(self._data.keys())
