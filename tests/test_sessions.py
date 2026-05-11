"""Session-store unit tests.

Covers the optimistic-locking semantics that protect /chat against
concurrent writes losing data. The Postgres implementation has the same
contract via a conditional UPDATE — these tests exercise it through the
in-memory store, which is the codebase's reference implementation for
the SessionStore Protocol.
"""

from __future__ import annotations

import pytest

from src.agent.state import ConversationState
from src.sessions import InMemorySessionStore, SessionConflict


@pytest.mark.asyncio
async def test_put_initial_increments_version_from_zero() -> None:
    """A fresh state with version=0 should round-trip to version=1 after put."""
    store = InMemorySessionStore()
    state = ConversationState()
    assert state.version == 0

    await store.put(state)
    assert state.version == 1

    loaded = await store.get(state.session_id)
    assert loaded is not None
    assert loaded.version == 1
    assert loaded.session_id == state.session_id


@pytest.mark.asyncio
async def test_put_increments_version_on_each_successful_write() -> None:
    """Successive puts on the same state should monotonically bump version."""
    store = InMemorySessionStore()
    state = ConversationState()

    for expected_version in (1, 2, 3, 4):
        await store.put(state)
        assert state.version == expected_version


@pytest.mark.asyncio
async def test_concurrent_writers_one_wins_one_conflicts() -> None:
    """Two writers loading the same session, both editing, then both putting:
    the second one MUST raise SessionConflict — otherwise the first writer's
    work is silently overwritten."""
    store = InMemorySessionStore()
    initial = ConversationState()
    await store.put(initial)  # version is now 1

    # Both writers load the session at version=1.
    writer_a = await store.get(initial.session_id)
    writer_b = await store.get(initial.session_id)
    assert writer_a is not None and writer_b is not None
    assert writer_a.version == 1 and writer_b.version == 1

    # Writer A applies their edit and writes — succeeds, version goes 1 → 2.
    writer_a.messages.append({"role": "user", "content": "A's message"})
    await store.put(writer_a)
    assert writer_a.version == 2

    # Writer B (still at version=1) tries to write — must fail, otherwise
    # A's message is lost.
    writer_b.messages.append({"role": "user", "content": "B's message"})
    with pytest.raises(SessionConflict):
        await store.put(writer_b)
    # B's version is unchanged — the store rejected the write.
    assert writer_b.version == 1

    # A's data is intact on disk; B's never landed.
    final = await store.get(initial.session_id)
    assert final is not None
    assert final.version == 2
    assert final.messages == [{"role": "user", "content": "A's message"}]


@pytest.mark.asyncio
async def test_caller_can_retry_after_conflict() -> None:
    """The standard recovery pattern: catch SessionConflict, refetch, retry."""
    store = InMemorySessionStore()
    initial = ConversationState()
    await store.put(initial)

    stale = await store.get(initial.session_id)
    assert stale is not None

    # Someone else writes first.
    other = await store.get(initial.session_id)
    assert other is not None
    other.messages.append({"role": "user", "content": "winner"})
    await store.put(other)

    # Our stale write fails.
    stale.messages.append({"role": "user", "content": "loser"})
    with pytest.raises(SessionConflict):
        await store.put(stale)

    # Recovery: refetch, re-apply our intent, write again.
    fresh = await store.get(initial.session_id)
    assert fresh is not None
    fresh.messages.append({"role": "user", "content": "loser-retried"})
    await store.put(fresh)

    final = await store.get(initial.session_id)
    assert final is not None
    assert [m["content"] for m in final.messages] == ["winner", "loser-retried"]


@pytest.mark.asyncio
async def test_delete_then_put_treats_as_first_write() -> None:
    """After delete, the in-memory store treats the session as never having
    existed. A subsequent put with stale state should not raise — the row
    is gone, so the version check doesn't fire."""
    store = InMemorySessionStore()
    state = ConversationState()
    await store.put(state)  # version=1
    await store.delete(state.session_id)

    # state.version is still 1 in memory, but the store has no record.
    # The next put treats this as a first write — the InMemoryStore's
    # contract is "existing is None → no version check."
    await store.put(state)
    assert state.version == 2

    final = await store.get(state.session_id)
    assert final is not None
    assert final.version == 2


# ---------------------------------------------------------------------------
# Postgres-store regression — exercise the actual SQL path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_postgres_store_updates_legacy_row_with_version_zero(seeded_db: None) -> None:
    """Regression — Phase 1.13: a session row that pre-dates the version
    column gets version=0 from the migration's DEFAULT. The next put()
    must UPDATE in place, not try to INSERT (which would fail on the
    UNIQUE constraint on session_id).

    This is the exact production crash the user hit on 2026-05-11:
    legacy session created before deploy → migration added version=0 →
    next chat turn called put() → old code branched on version==0,
    tried INSERT, hit UniqueViolationError.
    """
    from sqlalchemy import insert as sa_insert

    from src.db import get_async_session
    from src.db.models import SessionRow
    from src.sessions import PostgresSessionStore

    # Seed a "legacy" row directly via SQL — bypassing put() so we get
    # the exact shape a migrated pre-1.13 row would have: version=0 and
    # state_json without a version field inside.
    legacy_session_id = "legacy-session-id-pre-1.13"
    legacy_state_json = (
        '{"session_id":"' + legacy_session_id + '",'
        '"created_at":"2026-05-01T00:00:00Z",'
        '"updated_at":"2026-05-01T00:00:00Z",'
        '"messages":[{"role":"user","content":"first turn"}],'
        '"trace":[],'
        '"total_input_tokens":100,"total_output_tokens":200,"total_turns":1}'
        # Note: NO version field — matches the pre-1.13 shape exactly.
    )
    async with get_async_session() as session:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.execute(
            sa_insert(SessionRow).values(
                session_id=legacy_session_id,
                state_json=legacy_state_json,
                version=0,  # migration default
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    store = PostgresSessionStore()

    # Load it — version should be 0 (from the row, NOT from the JSON
    # which doesn't carry the field).
    loaded = await store.get(legacy_session_id)
    assert loaded is not None
    assert loaded.version == 0
    assert loaded.total_turns == 1

    # Mutate as a normal chat turn would, then put back.
    loaded.messages.append({"role": "assistant", "content": "second turn"})
    loaded.total_turns = 2
    # This is the operation that crashed on 2026-05-11 with
    # UniqueViolationError. Must succeed now.
    await store.put(loaded)
    assert loaded.version == 1  # bumped exactly once

    # Verify the row was actually updated, not duplicated.
    reloaded = await store.get(legacy_session_id)
    assert reloaded is not None
    assert reloaded.version == 1
    assert reloaded.total_turns == 2
    assert len(reloaded.messages) == 2


@pytest.mark.asyncio
async def test_postgres_store_conflict_path_via_sql(seeded_db: None) -> None:
    """Postgres path — two callers loading the same row, both writing,
    second must SessionConflict. Mirrors test_concurrent_writers_one_wins_one_conflicts
    but goes through the SQL path so the WHERE-clause check fires."""
    from src.sessions import PostgresSessionStore, SessionConflict

    store = PostgresSessionStore()

    # Seed via the store itself so versions are clean.
    initial = ConversationState()
    await store.put(initial)
    assert initial.version == 1

    writer_a = await store.get(initial.session_id)
    writer_b = await store.get(initial.session_id)
    assert writer_a is not None and writer_b is not None
    assert writer_a.version == 1 and writer_b.version == 1

    writer_a.messages.append({"role": "user", "content": "A wins"})
    await store.put(writer_a)
    assert writer_a.version == 2

    writer_b.messages.append({"role": "user", "content": "B loses"})
    with pytest.raises(SessionConflict):
        await store.put(writer_b)
    # B's version unchanged in memory; row on disk still at A's version.
    assert writer_b.version == 1

    final = await store.get(initial.session_id)
    assert final is not None
    assert final.version == 2
    assert [m["content"] for m in final.messages] == ["A wins"]
