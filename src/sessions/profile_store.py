"""User profile storage — Pydantic models, Protocol, and concrete stores.

Mirrors the SessionStore pattern from ADR-004:
  - Protocol defined here (`ProfileStore`)
  - In-memory implementation for tests (`InMemoryProfileStore`)
  - Postgres implementation for production (`PostgresProfileStore`)

Profile lifecycle:
  - Created via POST /profile (returns profile_id)
  - Stored client-side in localStorage
  - Sent with each /chat as `profile_id`
  - Backend fetches it once per turn and injects a personalisation fragment
    into the system prompt for that turn (NOT persisted in messages — it's
    fresh context every turn so prompt updates take effect immediately on
    every existing session)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session
from src.db.models import UserProfileRow

# ---------------------------------------------------------------------------
# Datetime convention
# ---------------------------------------------------------------------------
#
# Pydantic boundary:  tz-aware UTC (datetime.now(timezone.utc))
# Postgres column:    TIMESTAMP WITHOUT TIME ZONE (the SQLModel default)
#
# `_to_naive_utc` and `_to_aware_utc` translate at the storage boundary so
# the API stays explicit-UTC while DB rows match SQLModel's default schema.
# Same convention will apply when sessions move to Postgres in Phase 1.12b.


def _to_naive_utc(dt: datetime) -> datetime:
    """Drop tzinfo (after converting to UTC) — for writing to Postgres."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _to_aware_utc(dt: datetime) -> datetime:
    """Attach UTC tzinfo to a naive datetime read from the DB."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

# ---------------------------------------------------------------------------
# Pydantic models — the API + agent boundary
# ---------------------------------------------------------------------------

ExperienceLevel = Literal["beginner", "casual", "intermediate", "experienced", "racer"]
TripStyle = Literal["weekend", "touring", "commute", "charity", "special", "solo"]
Priority = Literal[
    "scenery",
    "distance",
    "food_drink",
    "wild_camping",
    "quiet_roads",
    "pubs_culture",
    "cheap",
    "iconic",
    "photography",
]
DietaryRestriction = Literal[
    "vegetarian", "vegan", "gluten_free", "halal", "kosher", "lactose_free", "none"
]

# Default daily km comfort by experience level — the agent uses this as the
# "don't push past their comfort distance unsolicited" threshold.
_COMFORT_BY_EXPERIENCE: dict[ExperienceLevel, int] = {
    "beginner": 50,
    "casual": 80,
    "intermediate": 100,
    "experienced": 130,
    "racer": 180,
}


class UserProfile(BaseModel):
    """The profile the agent reasons over.

    `profile_id` is a UUID4 generated client-side (so the client controls
    its own identity, no auth required). Server validates the format.
    """

    profile_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    experience: ExperienceLevel
    max_daily_km_comfort: int = Field(ge=20, le=300)
    trip_styles: list[TripStyle] = Field(default_factory=list)
    priorities: list[Priority] = Field(
        default_factory=list,
        description="What the cyclist cares about most. The agent biases route and accommodation choices toward these.",
    )
    dietary: list[DietaryRestriction] = Field(default_factory=list)
    additional_notes: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("profile_id")
    @classmethod
    def _validate_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as e:
            raise ValueError(f"profile_id must be a valid UUID, got {v!r}") from e
        return v


class UserProfileCreate(BaseModel):
    """Body for POST /profile.

    `profile_id` is optional — if omitted, the server generates a fresh UUID4
    and returns it. Clients send the same id back on update to upsert.
    """

    profile_id: str | None = None
    experience: ExperienceLevel
    trip_styles: list[TripStyle] = Field(default_factory=list)
    priorities: list[Priority] = Field(default_factory=list)
    dietary: list[DietaryRestriction] = Field(default_factory=list)
    additional_notes: str | None = Field(default=None, max_length=500)

    def to_profile(self) -> UserProfile:
        """Materialise a full UserProfile, deriving max_daily_km_comfort
        from the experience level."""
        return UserProfile(
            profile_id=self.profile_id or str(uuid.uuid4()),
            experience=self.experience,
            max_daily_km_comfort=_COMFORT_BY_EXPERIENCE[self.experience],
            trip_styles=self.trip_styles,
            priorities=self.priorities,
            dietary=self.dietary,
            additional_notes=self.additional_notes,
        )


# ---------------------------------------------------------------------------
# Storage layer
# ---------------------------------------------------------------------------


@runtime_checkable
class ProfileStore(Protocol):
    """Contract every profile store implements.

    Async even for in-memory so the interface stays identical when the
    Postgres implementation becomes I/O-bound.
    """

    async def get(self, profile_id: str) -> UserProfile | None: ...

    async def upsert(self, profile: UserProfile) -> UserProfile: ...

    async def delete(self, profile_id: str) -> bool: ...


class InMemoryProfileStore:
    """Process-local dict. Used by tests with a SQLite engine swapped in;
    in dev where DATABASE_URL is unset, falls back to this too."""

    def __init__(self) -> None:
        self._data: dict[str, UserProfile] = {}
        self._lock = asyncio.Lock()

    async def get(self, profile_id: str) -> UserProfile | None:
        return self._data.get(profile_id)

    async def upsert(self, profile: UserProfile) -> UserProfile:
        async with self._lock:
            existing = self._data.get(profile.profile_id)
            now = datetime.now(timezone.utc)
            if existing is not None:
                profile.created_at = existing.created_at
            profile.updated_at = now
            self._data[profile.profile_id] = profile
            return profile

    async def delete(self, profile_id: str) -> bool:
        async with self._lock:
            return self._data.pop(profile_id, None) is not None


class PostgresProfileStore:
    """Persists profiles in the `user_profiles` Postgres table.

    Same connection pool as everything else in `src.db.engine` — no separate
    config needed. Falls back to the SQLite in-memory engine if DATABASE_URL
    is unset, which is how tests exercise this code path.
    """

    async def get(self, profile_id: str) -> UserProfile | None:
        async with get_async_session() as session:
            row = await self._fetch(session, profile_id)
            return _row_to_profile(row) if row else None

    async def upsert(self, profile: UserProfile) -> UserProfile:
        now_naive = _to_naive_utc(datetime.now(timezone.utc))
        async with get_async_session() as session:
            existing = await self._fetch(session, profile.profile_id)
            if existing is None:
                row = UserProfileRow(
                    profile_id=profile.profile_id,
                    experience=profile.experience,
                    max_daily_km_comfort=profile.max_daily_km_comfort,
                    trip_styles_json=json.dumps(profile.trip_styles),
                    priorities_json=json.dumps(profile.priorities),
                    dietary_json=json.dumps(profile.dietary),
                    additional_notes=profile.additional_notes,
                    created_at=now_naive,
                    updated_at=now_naive,
                )
                session.add(row)
            else:
                existing.experience = profile.experience
                existing.max_daily_km_comfort = profile.max_daily_km_comfort
                existing.trip_styles_json = json.dumps(profile.trip_styles)
                existing.priorities_json = json.dumps(profile.priorities)
                existing.dietary_json = json.dumps(profile.dietary)
                existing.additional_notes = profile.additional_notes
                existing.updated_at = now_naive
            await session.commit()

            # Re-fetch to return the canonical view (timestamps, etc.)
            row = await self._fetch(session, profile.profile_id)
            assert row is not None
            return _row_to_profile(row)

    async def delete(self, profile_id: str) -> bool:
        async with get_async_session() as session:
            row = await self._fetch(session, profile_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    @staticmethod
    async def _fetch(session: AsyncSession, profile_id: str) -> UserProfileRow | None:
        result = await session.execute(
            select(UserProfileRow).where(UserProfileRow.profile_id == profile_id)
        )
        return result.scalar_one_or_none()


def _row_to_profile(row: UserProfileRow) -> UserProfile:
    """Hydrate a UserProfile from a UserProfileRow. JSON-decodes the list cols
    and re-attaches UTC tzinfo to the naive timestamps."""
    return UserProfile(
        profile_id=row.profile_id,
        experience=row.experience,  # type: ignore[arg-type]
        max_daily_km_comfort=row.max_daily_km_comfort,
        trip_styles=json.loads(row.trip_styles_json or "[]"),
        priorities=json.loads(row.priorities_json or "[]"),
        dietary=json.loads(row.dietary_json or "[]"),
        additional_notes=row.additional_notes,
        created_at=_to_aware_utc(row.created_at),
        updated_at=_to_aware_utc(row.updated_at),
    )


# Suppress unused-import errors for the dialect-specific insert helpers we
# imported above. They're held for a future "true upsert via ON CONFLICT"
# optimisation but the read-then-update path is fine for case-study scale.
_ = pg_insert
_ = sqlite_insert
