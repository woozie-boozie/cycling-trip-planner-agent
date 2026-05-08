"""Session store — interface and in-memory implementation.

The Protocol defines the contract that a Postgres-backed implementation will
satisfy in Phase 1.12. By committing to this shape now, the swap is one line
in `src/api/dependencies.py` rather than a refactor.

Methods are async even for the in-memory case so the interface stays identical
when the real implementation becomes I/O-bound.
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

from src.agent.state import ConversationState


@runtime_checkable
class SessionStore(Protocol):
    """The contract every session store must satisfy."""

    async def get(self, session_id: str) -> ConversationState | None:
        ...

    async def put(self, state: ConversationState) -> None:
        ...

    async def delete(self, session_id: str) -> bool:
        ...

    async def list_ids(self) -> list[str]:
        ...


class InMemorySessionStore:
    """Process-local dict. Sessions reset on server restart — acceptable for
    the case-study spec ("conversation state" doesn't imply durability).

    Thread/coroutine-safe via an asyncio.Lock guarding mutations.
    """

    def __init__(self) -> None:
        self._data: dict[str, ConversationState] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str) -> ConversationState | None:
        return self._data.get(session_id)

    async def put(self, state: ConversationState) -> None:
        async with self._lock:
            state.touch()
            self._data[state.session_id] = state

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            return self._data.pop(session_id, None) is not None

    async def list_ids(self) -> list[str]:
        return list(self._data.keys())
