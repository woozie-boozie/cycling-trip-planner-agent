"""HTTP API tests.

We test the *routing* and the *contract*: status codes, request/response
schemas, session lifecycle, and 404 behavior. The agent loop itself is
exercised via a mocked Anthropic client (reusing the fakes from test_agent.py
patterns) so no real tokens are burned.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Importing src.tools registers all tools — needed because dispatch() runs
# during the agent loop in chat tests.
import src.tools  # noqa: F401
from src.agent.config import _clear_settings_cache
from src.api.dependencies import get_anthropic_client, get_session_store
from src.api.main import app
from src.sessions import InMemorySessionStore


# ---------------------------------------------------------------------------
# Fake Anthropic client — same pattern used in test_agent.py
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
class FakeToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"

    def model_dump(self, **_: Any) -> dict[str, Any]:
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}


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


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    _clear_settings_cache()
    yield
    _clear_settings_cache()


@pytest.fixture
def fresh_store() -> InMemorySessionStore:
    """Each test gets a fresh store so they're isolated."""
    return InMemorySessionStore()


@pytest.fixture
def client(fresh_store: InMemorySessionStore) -> Iterator[TestClient]:
    """A TestClient with the session store overridden to a per-test fixture
    and the Anthropic client overridden per-test via `set_fake_client`."""
    app.dependency_overrides[get_session_store] = lambda: fresh_store

    yield TestClient(app)

    app.dependency_overrides.clear()


def set_fake_client(responses: list[FakeResponse]) -> MagicMock:
    """Override the Anthropic client dependency with a queue of fake responses."""
    fake = make_fake_client(responses)
    app.dependency_overrides[get_anthropic_client] = lambda: fake
    return fake


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "cycling-trip-planner-agent"


def test_root(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_openapi_includes_chat_endpoint(client: TestClient) -> None:
    """If the OpenAPI doc misses /chat, the swagger /docs page is broken."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/chat" in paths
    assert "post" in paths["/chat"]


# ---------------------------------------------------------------------------
# /chat — happy paths
# ---------------------------------------------------------------------------


def test_chat_creates_new_session_when_no_id_given(client: TestClient) -> None:
    set_fake_client(
        [
            FakeResponse(
                content=[FakeTextBlock(text="Hi! What's your route idea?")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=10, output_tokens=20),
            )
        ]
    )

    resp = client.post("/chat", json={"message": "Hi"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"]  # generated
    assert body["message"] == "Hi! What's your route idea?"
    assert body["stop_reason"] == "end_turn"
    assert body["iterations"] == 1
    assert body["input_tokens"] == 10
    assert body["output_tokens"] == 20


def test_chat_resumes_existing_session(client: TestClient) -> None:
    # First turn — creates session
    set_fake_client(
        [
            FakeResponse(
                content=[FakeTextBlock(text="What daily distance?")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=10, output_tokens=10),
            )
        ]
    )
    first = client.post("/chat", json={"message": "Plan a trip"})
    session_id = first.json()["session_id"]

    # Second turn — resume
    set_fake_client(
        [
            FakeResponse(
                content=[FakeTextBlock(text="Great, planning for 100km/day.")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=30, output_tokens=15),
            )
        ]
    )
    second = client.post("/chat", json={"message": "100km a day", "session_id": session_id})
    assert second.status_code == 200
    body = second.json()
    assert body["session_id"] == session_id
    assert body["message"] == "Great, planning for 100km/day."


def test_chat_with_real_tool_dispatch(client: TestClient) -> None:
    """Mock Claude into asking for `get_route` — verify the agent dispatches
    our actual tool registry, not a mock."""
    set_fake_client(
        [
            FakeResponse(
                content=[
                    FakeToolUseBlock(
                        id="tu_1",
                        name="get_route",
                        input={"start": "Amsterdam", "end": "Copenhagen"},
                    )
                ],
                stop_reason="tool_use",
                usage=FakeUsage(input_tokens=50, output_tokens=80),
            ),
            FakeResponse(
                content=[FakeTextBlock(text="850km via the Fehmarn ferry.")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=400, output_tokens=20),
            ),
        ]
    )
    resp = client.post("/chat", json={"message": "Distance?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["iterations"] == 2
    assert body["message"] == "850km via the Fehmarn ferry."
    assert any(call["name"] == "get_route" for call in body["tool_calls"])


# ---------------------------------------------------------------------------
# /chat — error paths
# ---------------------------------------------------------------------------


def test_chat_unknown_session_id_returns_404(client: TestClient) -> None:
    """Don't silently create a new session for a bogus id — that masks bugs."""
    resp = client.post(
        "/chat",
        json={"message": "Hi", "session_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


def test_chat_empty_message_rejected(client: TestClient) -> None:
    resp = client.post("/chat", json={"message": ""})
    assert resp.status_code == 422  # pydantic min_length=1


def test_chat_oversized_message_rejected(client: TestClient) -> None:
    resp = client.post("/chat", json={"message": "x" * 5000})
    assert resp.status_code == 422  # max_length=4000


# ---------------------------------------------------------------------------
# /sessions
# ---------------------------------------------------------------------------


def test_sessions_lifecycle(client: TestClient) -> None:
    # Initially empty
    assert client.get("/sessions").json() == {"session_ids": [], "count": 0}

    # Start a session
    set_fake_client(
        [
            FakeResponse(
                content=[FakeTextBlock(text="ok")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=5, output_tokens=5),
            )
        ]
    )
    chat_resp = client.post("/chat", json={"message": "Plan"})
    sid = chat_resp.json()["session_id"]

    # List shows it
    listing = client.get("/sessions").json()
    assert sid in listing["session_ids"]
    assert listing["count"] == 1

    # Detail returns full state
    detail = client.get(f"/sessions/{sid}").json()
    assert detail["session_id"] == sid
    assert detail["total_turns"] == 1
    assert len(detail["messages"]) == 2  # user + assistant

    # Delete
    deletion = client.delete(f"/sessions/{sid}").json()
    assert deletion == {"deleted": True}

    # Gone
    assert client.get(f"/sessions/{sid}").status_code == 404
    assert client.delete(f"/sessions/{sid}").status_code == 404


def test_get_session_unknown_returns_404(client: TestClient) -> None:
    assert client.get("/sessions/no-such-id").status_code == 404


# ---------------------------------------------------------------------------
# /trace
# ---------------------------------------------------------------------------


def test_trace_returns_events_in_order(client: TestClient) -> None:
    set_fake_client(
        [
            FakeResponse(
                content=[
                    FakeTextBlock(text="checking..."),
                    FakeToolUseBlock(
                        id="tu_x",
                        name="get_weather",
                        input={"location": "Amsterdam", "month": "June"},
                    ),
                ],
                stop_reason="tool_use",
                usage=FakeUsage(input_tokens=20, output_tokens=15),
            ),
            FakeResponse(
                content=[FakeTextBlock(text="It's mild.")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=80, output_tokens=10),
            ),
        ]
    )
    chat_resp = client.post("/chat", json={"message": "Weather in Amsterdam in June?"})
    sid = chat_resp.json()["session_id"]

    trace_resp = client.get(f"/trace/{sid}")
    assert trace_resp.status_code == 200
    body = trace_resp.json()
    types = [e["type"] for e in body["events"]]
    assert types[0] == "user_message"
    assert "tool_use" in types
    assert "tool_result" in types
    assert types[-1] == "stop"
    assert body["event_count"] == len(body["events"])
    assert body["total_input_tokens"] == 100
    assert body["total_output_tokens"] == 25
    # Cost estimate sanity: (100 * 3 + 25 * 15) / 1e6 = 0.000675
    assert 0 < body["estimated_cost_usd"] < 0.01


def test_trace_unknown_session_returns_404(client: TestClient) -> None:
    assert client.get("/trace/no-such-id").status_code == 404
