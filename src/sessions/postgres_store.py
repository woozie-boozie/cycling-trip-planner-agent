"""PostgresSessionStore — durable conversation state for Cloud Run.

Why this exists (Phase 1.12b):
  Cloud Run scales to zero. A cold start spins up a new container, which
  means the in-memory `_data` dict in `InMemorySessionStore` starts empty.
  Any `session_id` the client has in localStorage from before the cold
  start returns 404. Reviewers see "broken multi-turn." This store fixes
  that by persisting state to the same Neon Postgres instance the
  ProfileStore + tool data already use.

Storage shape:
  ConversationState is Pydantic top-to-bottom — every field round-trips
  through `model_dump_json()` losslessly. So we don't relationally model
  the messages / trace events. We store one row per session, with the
  whole state as a JSON blob in `state_json`. See `SessionRow` for the
  full reasoning.

Datetime convention:
  Same as `PostgresProfileStore` (`_to_naive_utc` / `_to_aware_utc`):
  tz-aware UTC at the Pydantic boundary, tz-naive UTC in Postgres
  `TIMESTAMP WITHOUT TIME ZONE`. Bug 24 (visible in self-test 23 of the
  build journal) is the canonical "test in SQLite, verify in Postgres"
  lesson — apply the same translation here.

Failure model:
  Any DB error during put/get/delete logs at WARNING and surfaces the
  exception. Callers (the chat endpoint) can decide whether to fall back
  or fail loudly. The retry-on-404 logic in the frontend already handles
  the "session disappeared" case for us — same recovery contract as the
  in-memory store.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import structlog
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.state import ConversationState
from src.db import get_async_session
from src.db.models import SessionRow
from src.sessions.store import SessionConflict

log = structlog.get_logger(__name__)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def _to_naive_utc(dt: datetime) -> datetime:
    """Drop tzinfo (after converting to UTC) — for writing to Postgres."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _row_to_state(row: SessionRow) -> ConversationState:
    """Deserialise the JSON blob into ConversationState.

    The row's ``version`` column is the authoritative version; the JSON blob
    carries the same value (kept in sync by ``put``). We trust the JSON
    here — Pydantic defaults ``version=0`` for pre-1.13 rows whose
    serialised blob predates the field, then the next ``put`` brings it
    into sync with ``row.version``.
    """
    state = ConversationState.model_validate_json(row.state_json)
    # Postgres column is authoritative — overrides JSON for pre-1.13 rows
    # whose blob was written without a version field.
    state.version = row.version
    return state


class PostgresSessionStore:
    """Postgres-backed session store with optimistic-locking semantics.

    Concurrent writers to the same ``session_id`` are detected via a
    conditional UPDATE keyed on ``version``. The loser sees rowcount=0 and
    is raised as :class:`SessionConflict`; callers convert this to HTTP
    409 so the client can refetch + retry.

    Why not pessimistic ``SELECT … FOR UPDATE``: the read-modify-write
    window spans an entire agent turn (often 10–30 s of Anthropic calls).
    Holding a row lock that long blocks unrelated reads (e.g. the trace
    panel) and risks deadlocks under fan-out. Optimistic locking pushes
    the conflict to write time, which is microseconds — the right scope
    for this access pattern.
    """

    async def get(self, session_id: str) -> ConversationState | None:
        try:
            async with get_async_session() as session:
                result = await session.execute(
                    select(SessionRow).where(SessionRow.session_id == session_id)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                return _row_to_state(row)
        except Exception as e:
            log.warning("session.get.failed", session_id=session_id, error=str(e))
            raise

    async def put(self, state: ConversationState) -> None:
        """Persist ``state`` with optimistic-locking version check.

        Two-statement pattern (SELECT current version → conditional
        INSERT/UPDATE) for dialect-agnostic correctness:

          1. SELECT the current version for this session_id.
          2a. No row → INSERT. If a concurrent writer beat us to it,
              the UNIQUE constraint raises IntegrityError → SessionConflict.
          2b. Row exists AND version matches state.version → UPDATE with
              a redundant ``WHERE version = :expected_version``. If
              rowcount=0, another writer slipped in between our SELECT
              and UPDATE → SessionConflict.
          2c. Row exists BUT version drifted → SessionConflict immediately.

        Why not a single ``INSERT ... ON CONFLICT DO UPDATE WHERE``:
        the rowcount semantics of ON CONFLICT differ across Postgres
        and SQLite (Postgres reports 0 when the WHERE filters the
        UPDATE; SQLite reports 1). The two-statement pattern is more
        verbose but rock-solid on both engines, and session writes are
        one-per-chat-turn — not a hot path. The extra roundtrip is
        negligible.

        On success, ``state.version`` is incremented in-place so the
        caller can chain another ``put`` without re-fetching.
        """
        state.touch()
        expected_version = state.version
        new_version = expected_version + 1
        now_naive = _to_naive_utc(datetime.now(timezone.utc))

        # Serialise with the new version baked in so the JSON blob and
        # the version column stay in sync from the very first write.
        state.version = new_version
        payload = state.model_dump_json()
        state.version = expected_version

        try:
            async with get_async_session() as session:
                # Step 1 — read current on-disk version.
                read = await session.execute(
                    select(SessionRow.version).where(
                        SessionRow.session_id == state.session_id
                    )
                )
                on_disk_version = read.scalar_one_or_none()

                if on_disk_version is None:
                    # Step 2a — no row exists, INSERT. A concurrent INSERT
                    # races us to the unique constraint, surfaces as
                    # IntegrityError, which we translate to SessionConflict.
                    try:
                        await session.execute(
                            insert(SessionRow).values(
                                session_id=state.session_id,
                                state_json=payload,
                                version=new_version,
                                created_at=now_naive,
                                updated_at=now_naive,
                            )
                        )
                    except IntegrityError as e:
                        raise SessionConflict(
                            f"session {state.session_id!r} was created "
                            f"concurrently between get() and put()"
                        ) from e
                elif on_disk_version != expected_version:
                    # Step 2c — version drift detected at read time. No
                    # need to even attempt the UPDATE.
                    raise SessionConflict(
                        f"session {state.session_id!r} was modified "
                        f"concurrently (expected version {expected_version}, "
                        f"on-disk version {on_disk_version})"
                    )
                else:
                    # Step 2b — version matches, UPDATE with belt-and-braces
                    # WHERE that catches a concurrent UPDATE between our
                    # SELECT and our UPDATE.
                    result = await session.execute(
                        update(SessionRow)
                        .where(
                            SessionRow.session_id == state.session_id,
                            SessionRow.version == expected_version,
                        )
                        .values(
                            state_json=payload,
                            version=new_version,
                            updated_at=now_naive,
                        )
                    )
                    if (result.rowcount or 0) == 0:
                        raise SessionConflict(
                            f"session {state.session_id!r} was modified "
                            f"concurrently (expected version "
                            f"{expected_version}, UPDATE matched no rows)"
                        )

                await session.commit()
                state.version = new_version
        except SessionConflict:
            # Don't log at WARNING — conflict is an expected outcome of
            # concurrent writes, not a system failure. Let the caller
            # decide whether to surface it.
            raise
        except Exception as e:
            log.warning(
                "session.put.failed",
                session_id=state.session_id,
                error=str(e),
            )
            raise

    async def delete(self, session_id: str) -> bool:
        try:
            async with get_async_session() as session:
                result = await session.execute(
                    delete(SessionRow).where(SessionRow.session_id == session_id)
                )
                await session.commit()
                return (result.rowcount or 0) > 0
        except Exception as e:
            log.warning("session.delete.failed", session_id=session_id, error=str(e))
            raise

    async def list_ids(self) -> list[str]:
        async with get_async_session() as session:
            result = await session.execute(select(SessionRow.session_id))
            return [row[0] for row in result.all()]
