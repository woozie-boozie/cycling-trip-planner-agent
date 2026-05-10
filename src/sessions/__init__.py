"""Session + profile storage — abstractions over how state persists.

Two stores live here, with parallel Protocol + InMemory + (later) Postgres
shapes:
  - SessionStore — conversation state per session
  - ProfileStore — cyclist profile per user (Phase 2D)
"""

from src.sessions.profile_store import (
    DietaryRestriction,
    ExperienceLevel,
    InMemoryProfileStore,
    PostgresProfileStore,
    Priority,
    ProfileStore,
    TripStyle,
    UserProfile,
    UserProfileCreate,
)
from src.sessions.postgres_store import PostgresSessionStore
from src.sessions.store import InMemorySessionStore, SessionStore

__all__ = [
    # Sessions
    "InMemorySessionStore",
    "PostgresSessionStore",
    "SessionStore",
    # Profiles
    "DietaryRestriction",
    "ExperienceLevel",
    "InMemoryProfileStore",
    "PostgresProfileStore",
    "Priority",
    "ProfileStore",
    "TripStyle",
    "UserProfile",
    "UserProfileCreate",
]
