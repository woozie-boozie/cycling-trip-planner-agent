"""Tests for the user-profile layer (Phase 2D · backend).

Covers:
  - UserProfile / UserProfileCreate Pydantic validation
  - PostgresProfileStore upsert / get / delete (against the SQLite test fixture)
  - POST/GET/DELETE /profile endpoints
  - /chat threads the profile through to the agent (mocked Anthropic client
    so we can inspect what the system prompt contained)
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import src.tools  # noqa: F401  — register tools
from src.agent.config import _clear_settings_cache
from src.agent.prompts import user_profile_context
from src.api.dependencies import (
    get_anthropic_client,
    get_profile_store,
    get_session_store,
)
from src.api.main import app
from src.sessions import (
    InMemoryProfileStore,
    InMemorySessionStore,
    PostgresProfileStore,
    UserProfile,
    UserProfileCreate,
)


def _system_text(value: Any) -> str:
    """Helper for the chat-API tests below. The agent now passes ``system``
    as a list of cache-marked text blocks (prompt caching) rather than a
    bare string; this normalises both shapes back to a single concatenated
    string for substring assertions."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            block.get("text", "")
            for block in value
            if isinstance(block, dict)
        )
    return ""


# ---------------------------------------------------------------------------
# Pydantic boundary
# ---------------------------------------------------------------------------


def test_user_profile_create_derives_max_daily_km() -> None:
    """The frontend sends experience; the server derives the comfort threshold."""
    create = UserProfileCreate(experience="beginner")
    profile = create.to_profile()
    assert profile.experience == "beginner"
    assert profile.max_daily_km_comfort == 50

    create = UserProfileCreate(experience="racer", trip_styles=["solo"])
    profile = create.to_profile()
    assert profile.max_daily_km_comfort == 180


def test_user_profile_validates_uuid() -> None:
    with pytest.raises(ValueError, match="must be a valid UUID"):
        UserProfile(
            profile_id="not-a-uuid",
            experience="casual",
            max_daily_km_comfort=80,
        )


def test_user_profile_caps_priorities_at_3() -> None:
    """The brief calls for *focus* — max 3 priorities forces real ranking."""
    with pytest.raises(ValueError):
        UserProfileCreate(
            experience="casual",
            priorities=["scenery", "distance", "food_drink", "wild_camping"],  # 4
        )


# ---------------------------------------------------------------------------
# PostgresProfileStore (against SQLite via the seeded_db fixture)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_postgres_profile_store_upsert_get_delete(seeded_db: None) -> None:
    store = PostgresProfileStore()

    # Create
    pid = str(uuid.uuid4())
    profile = UserProfile(
        profile_id=pid,
        experience="intermediate",
        max_daily_km_comfort=100,
        trip_styles=["weekend", "touring"],
        priorities=["scenery", "quiet_roads"],
        dietary=["vegetarian"],
        additional_notes="charity ride",
    )
    saved = await store.upsert(profile)
    assert saved.profile_id == pid
    assert saved.experience == "intermediate"

    # Read
    fetched = await store.get(pid)
    assert fetched is not None
    assert fetched.priorities == ["scenery", "quiet_roads"]
    assert fetched.dietary == ["vegetarian"]
    assert fetched.additional_notes == "charity ride"

    # Update (same id → upsert path)
    profile.priorities = ["scenery"]
    profile.experience = "experienced"
    profile.max_daily_km_comfort = 130
    updated = await store.upsert(profile)
    assert updated.experience == "experienced"
    assert updated.max_daily_km_comfort == 130
    assert updated.priorities == ["scenery"]

    # Delete
    deleted = await store.delete(pid)
    assert deleted is True
    assert await store.get(pid) is None

    # Deleting again is a no-op (returns False)
    assert await store.delete(pid) is False


@pytest.mark.asyncio
async def test_postgres_profile_store_unknown_id_returns_none(seeded_db: None) -> None:
    store = PostgresProfileStore()
    assert await store.get(str(uuid.uuid4())) is None


# ---------------------------------------------------------------------------
# InMemoryProfileStore (parity with the Postgres impl)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_profile_store_round_trip() -> None:
    store = InMemoryProfileStore()
    pid = str(uuid.uuid4())
    profile = UserProfile(
        profile_id=pid,
        experience="casual",
        max_daily_km_comfort=80,
    )
    await store.upsert(profile)
    fetched = await store.get(pid)
    assert fetched is not None
    assert fetched.experience == "casual"
    assert await store.delete(pid) is True
    assert await store.get(pid) is None


# ---------------------------------------------------------------------------
# Prompt fragment
# ---------------------------------------------------------------------------


def test_user_profile_context_includes_key_fields() -> None:
    p = UserProfile(
        experience="beginner",
        max_daily_km_comfort=50,
        trip_styles=["weekend"],
        priorities=["scenery"],
        dietary=["vegan"],
        additional_notes="have asthma",
    )
    text = user_profile_context(p)
    assert "Cyclist profile" in text
    assert "beginner" in text
    assert "50 km" in text
    assert "weekend" in text
    assert "scenic routes" in text or "scenery" in text
    assert "vegan" in text
    assert "have asthma" in text
    # Must include the "don't set them up for failure" guidance
    assert "comfort distance" in text or "comfortable" in text


def test_user_profile_context_skips_empty_sections() -> None:
    """A minimally-filled profile shouldn't pad the prompt with blank sections."""
    p = UserProfile(experience="casual", max_daily_km_comfort=80)
    text = user_profile_context(p)
    assert "Trip style" not in text
    assert "Top priorities" not in text
    assert "Dietary" not in text
    assert "Notes from rider" not in text


# ---------------------------------------------------------------------------
# /profile endpoints (TestClient with overridden stores)
# ---------------------------------------------------------------------------


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"

    def model_dump(self, **_: Any) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


@dataclass
class FakeResponse:
    content: list[Any]
    stop_reason: str
    usage: FakeUsage


def make_fake_client(responses: list[FakeResponse]) -> MagicMock:
    client = MagicMock()
    queue = list(responses)

    async def fake_create(**_kwargs: Any) -> FakeResponse:
        if not queue:
            raise AssertionError("agent made more API calls than fake responses provided")
        return queue.pop(0)

    client.messages = MagicMock()
    client.messages.create = fake_create
    return client


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    _clear_settings_cache()
    yield
    _clear_settings_cache()


@pytest.fixture
def fresh_session_store() -> InMemorySessionStore:
    return InMemorySessionStore()


@pytest.fixture
def fresh_profile_store() -> InMemoryProfileStore:
    return InMemoryProfileStore()


@pytest.fixture
def client(
    fresh_session_store: InMemorySessionStore,
    fresh_profile_store: InMemoryProfileStore,
) -> Iterator[TestClient]:
    app.dependency_overrides[get_session_store] = lambda: fresh_session_store
    app.dependency_overrides[get_profile_store] = lambda: fresh_profile_store
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_profile_create_get_delete_lifecycle(client: TestClient) -> None:
    # POST /profile (no profile_id → server generates one)
    resp = client.post(
        "/profile",
        json={
            "experience": "intermediate",
            "trip_styles": ["weekend"],
            "priorities": ["scenery", "quiet_roads"],
            "dietary": ["vegetarian"],
            "additional_notes": "cycling for charity",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    pid = body["profile_id"]
    assert pid  # uuid string
    assert body["experience"] == "intermediate"
    assert body["max_daily_km_comfort"] == 100
    assert body["dietary"] == ["vegetarian"]

    # GET /profile/{id}
    fetched = client.get(f"/profile/{pid}").json()
    assert fetched["profile_id"] == pid
    assert fetched["additional_notes"] == "cycling for charity"

    # POST /profile with the same id → update (experience changes)
    upd = client.post(
        "/profile",
        json={
            "profile_id": pid,
            "experience": "experienced",
            "trip_styles": ["touring", "solo"],
            "priorities": ["distance"],
            "dietary": [],
        },
    )
    assert upd.status_code == 200
    upd_body = upd.json()
    assert upd_body["experience"] == "experienced"
    assert upd_body["max_daily_km_comfort"] == 130
    assert upd_body["priorities"] == ["distance"]

    # DELETE
    deletion = client.delete(f"/profile/{pid}").json()
    assert deletion == {"deleted": True}
    assert client.get(f"/profile/{pid}").status_code == 404


def test_get_profile_unknown_returns_404(client: TestClient) -> None:
    assert client.get(f"/profile/{uuid.uuid4()}").status_code == 404


def test_chat_with_unknown_profile_id_still_succeeds(client: TestClient) -> None:
    """Soft miss — backend should NOT 404 the chat just because the profile
    is unknown. Same contract as session expiry recovery."""
    fake = make_fake_client(
        [
            FakeResponse(
                content=[FakeTextBlock(text="ok")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=10, output_tokens=5),
            )
        ]
    )
    app.dependency_overrides[get_anthropic_client] = lambda: fake

    resp = client.post(
        "/chat",
        json={"message": "hi", "profile_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "ok"


def test_chat_with_known_profile_personalises_system_prompt(client: TestClient) -> None:
    """If profile_id resolves, the system prompt seen by Claude must include
    the personalisation fragment ('Cyclist profile')."""
    # Seed a profile via the API
    pid_resp = client.post(
        "/profile",
        json={
            "experience": "beginner",
            "priorities": ["scenery"],
            "additional_notes": "first multi-day trip",
        },
    )
    pid = pid_resp.json()["profile_id"]

    captured: dict[str, Any] = {}

    fake = MagicMock()

    async def fake_create(**kwargs: Any) -> FakeResponse:
        captured["system"] = kwargs.get("system")
        return FakeResponse(
            content=[FakeTextBlock(text="ok")],
            stop_reason="end_turn",
            usage=FakeUsage(input_tokens=10, output_tokens=5),
        )

    fake.messages = MagicMock()
    fake.messages.create = fake_create
    app.dependency_overrides[get_anthropic_client] = lambda: fake

    resp = client.post(
        "/chat",
        json={"message": "Plan a London → Brighton ride", "profile_id": pid},
    )
    assert resp.status_code == 200

    # System is now sent as a list of cache-marked text blocks (prompt
    # caching) — assert against the joined text rather than the raw value.
    system_text = _system_text(captured.get("system"))
    assert "Cyclist profile" in system_text
    assert "beginner" in system_text
    assert "first multi-day trip" in system_text


def test_chat_without_profile_id_keeps_base_system_prompt(client: TestClient) -> None:
    """Backwards compatibility — chat without profile_id must NOT include
    the personalisation fragment. Existing v1 behaviour preserved."""
    captured: dict[str, Any] = {}
    fake = MagicMock()

    async def fake_create(**kwargs: Any) -> FakeResponse:
        captured["system"] = kwargs.get("system")
        return FakeResponse(
            content=[FakeTextBlock(text="ok")],
            stop_reason="end_turn",
            usage=FakeUsage(input_tokens=10, output_tokens=5),
        )

    fake.messages = MagicMock()
    fake.messages.create = fake_create
    app.dependency_overrides[get_anthropic_client] = lambda: fake

    resp = client.post("/chat", json={"message": "hi"})
    assert resp.status_code == 200

    system_text = _system_text(captured.get("system"))
    assert "Cyclist profile" not in system_text
