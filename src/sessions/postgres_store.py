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
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.state import ConversationState
from src.db import get_async_session
from src.db.models import SessionRow

log = structlog.get_logger(__name__)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def _to_naive_utc(dt: datetime) -> datetime:
    """Drop tzinfo (after converting to UTC) — for writing to Postgres."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _row_to_state(row: SessionRow) -> ConversationState:
    """Deserialise the JSON blob, then re-attach tz-aware UTC datetimes
    in the parsed ConversationState (Pydantic re-parses datetimes on
    `model_validate_json`)."""
    return ConversationState.model_validate_json(row.state_json)


class PostgresSessionStore:
    """Postgres-backed session store. Same Protocol as InMemorySessionStore."""

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
        """Upsert by session_id. INSERT … ON CONFLICT (session_id) DO UPDATE
        keeps it atomic on both Postgres and SQLite (the test fixture)."""
        state.touch()
        payload = state.model_dump_json()
        now_naive = _to_naive_utc(datetime.now(timezone.utc))

        try:
            async with get_async_session() as session:
                bind = session.get_bind()
                dialect = bind.dialect.name if bind is not None else "postgresql"
                values = {
                    "session_id": state.session_id,
                    "state_json": payload,
                    "created_at": now_naive,
                    "updated_at": now_naive,
                }

                if dialect == "sqlite":
                    stmt = sqlite_insert(SessionRow).values(**values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["session_id"],
                        set_={
                            "state_json": payload,
                            "updated_at": now_naive,
                        },
                    )
                else:
                    stmt = pg_insert(SessionRow).values(**values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["session_id"],
                        set_={
                            "state_json": payload,
                            "updated_at": now_naive,
                        },
                    )

                await session.execute(stmt)
                await session.commit()
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
