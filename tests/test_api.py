"""HTTP API tests.

We test the *routing* and the *contract*: status codes, request/response
schemas, session lifecycle, and 404 behavior. The agent loop itself is
exercised via a mocked Anthropic client (reusing the fakes from test_agent.py
patterns) so no real tokens are burned.
"""

from __future__ import annotations

import json
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


def test_chat_with_real_tool_dispatch(client: TestClient, seeded_db: None) -> None:
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


def test_trace_returns_events_in_order(client: TestClient, seeded_db: None) -> None:
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


# ---------------------------------------------------------------------------
# Multimodal — Phase 2A · image attachments
# ---------------------------------------------------------------------------

# 1x1 transparent PNG, base64-encoded. Smallest valid Anthropic-acceptable
# image — any inspector will see it and return early; the test just needs
# the wire-format plumbing to land correctly.
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def test_chat_accepts_image_and_threads_it_into_user_message(
    client: TestClient,
) -> None:
    """A request with an image should: (a) return 200, (b) result in a
    user message whose content is a list with [image_block, text_block]
    in that exact order — the order Anthropic recommends for vision."""
    set_fake_client(
        [
            FakeResponse(
                content=[FakeTextBlock(text="I see your Komoot screenshot.")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=300, output_tokens=20),
            )
        ]
    )

    resp = client.post(
        "/chat",
        json={
            "message": "Plan a trip based on this route screenshot.",
            "image": {
                "media_type": "image/png",
                "base64_data": _TINY_PNG_B64,
            },
        },
    )
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["session_id"]

    # Inspect the persisted session — the first user message should be a
    # list (multimodal turn), not a string. First block = image, second
    # = text. Order is load-bearing: Anthropic vision documentation
    # recommends image first.
    sess = client.get(f"/sessions/{session_id}")
    assert sess.status_code == 200
    messages = sess.json()["messages"]
    first = messages[0]
    assert first["role"] == "user"
    content = first["content"]
    assert isinstance(content, list), f"expected list of blocks, got {type(content)}"
    assert content[0]["type"] == "image"
    assert content[0]["source"]["type"] == "base64"
    assert content[0]["source"]["media_type"] == "image/png"
    assert content[0]["source"]["data"] == _TINY_PNG_B64
    assert content[1]["type"] == "text"
    assert content[1]["text"] == "Plan a trip based on this route screenshot."


def test_chat_rejects_malformed_base64_with_422(client: TestClient) -> None:
    """A junk-base64 payload should be rejected at the validation boundary,
    not bubble up as an opaque 500 from inside the agent loop."""
    # No fake client needed — the request must fail validation before
    # reaching the agent.
    resp = client.post(
        "/chat",
        json={
            "message": "Plan from this screenshot",
            "image": {
                "media_type": "image/png",
                "base64_data": "this is not actually base64!!!",
            },
        },
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    # FastAPI returns validation errors as a list of dicts; we just need
    # to confirm the offending field is base64_data.
    assert any("base64" in str(err).lower() for err in detail), detail


def test_chat_rejects_unsupported_image_mime_type(client: TestClient) -> None:
    """media_type is a Literal — anything outside the supported set must
    be rejected at the boundary so the agent never sees an invalid
    image content block."""
    resp = client.post(
        "/chat",
        json={
            "message": "Plan",
            "image": {
                "media_type": "image/heic",  # not in supported set
                "base64_data": _TINY_PNG_B64,
            },
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /chat/stream — SSE streaming endpoint
# ---------------------------------------------------------------------------

from types import SimpleNamespace


def _ns(**kw: Any) -> SimpleNamespace:
    """Tiny helper — SDK events expose attributes; we mimic with SimpleNamespace."""
    return SimpleNamespace(**kw)


class _FakeStream:
    """Minimal stand-in for ``anthropic.MessageStream``.

    Supports the surface the orchestrator's streaming.py uses:
      - async-iterable yielding event objects with ``.type`` + variant fields
      - ``current_message_snapshot.content`` for tool_use input extraction
    """

    def __init__(self, events: list[Any], snapshot: Any | None = None) -> None:
        self._events = events
        self._idx = 0
        self.current_message_snapshot = snapshot or _ns(content=[])

    def __aiter__(self) -> "_FakeStream":
        return self

    async def __anext__(self) -> Any:
        if self._idx >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._idx]
        self._idx += 1
        return event


class _FakeStreamManager:
    """Async context manager wrapping a ``_FakeStream``."""

    def __init__(self, events: list[Any], snapshot: Any | None = None) -> None:
        self._stream = _FakeStream(events, snapshot)

    async def __aenter__(self) -> _FakeStream:
        return self._stream

    async def __aexit__(self, *_: Any) -> bool:
        return False


class _FakeStreamRaisesOnEnter:
    """Async context manager that raises on entry — simulates an Anthropic
    transport error before any SSE event is yielded."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def __aenter__(self) -> _FakeStream:
        raise self._exc

    async def __aexit__(self, *_: Any) -> bool:
        return False


def _set_fake_stream(events: list[Any], snapshot: Any | None = None) -> MagicMock:
    """Inject a fake Anthropic client whose ``messages.stream(...)``
    returns a scripted event sequence."""
    fake = MagicMock()
    fake.messages = MagicMock()
    fake.messages.stream = lambda **_: _FakeStreamManager(events, snapshot)
    app.dependency_overrides[get_anthropic_client] = lambda: fake
    return fake


def _set_fake_stream_raising(exc: Exception) -> MagicMock:
    fake = MagicMock()
    fake.messages = MagicMock()
    fake.messages.stream = lambda **_: _FakeStreamRaisesOnEnter(exc)
    app.dependency_overrides[get_anthropic_client] = lambda: fake
    return fake


def _collect_sse_events(client: TestClient, body: dict[str, Any]) -> list[dict[str, Any]]:
    """POST to /chat/stream and decode every ``data: {...}`` line into a list
    of parsed event dicts. SSE empty separator lines are skipped."""
    events: list[dict[str, Any]] = []
    with client.stream("POST", "/chat/stream", json=body) as response:
        assert response.status_code == 200, response.text
        for raw in response.iter_lines():
            if not raw.startswith("data: "):
                continue
            events.append(json.loads(raw[6:]))
    return events


def test_chat_stream_text_only_emits_text_delta_and_completes(client: TestClient) -> None:
    """A text-only iteration should produce a session preamble, text_delta
    events for each token chunk, an iteration_end event, and a final done
    event with token accounting."""
    # Scripted SDK events: message_start (with usage), then content_block_start
    # for a text block, three text_delta events, content_block_stop, and
    # message_delta with stop_reason=end_turn + final output_tokens.
    events: list[Any] = [
        _ns(
            type="message_start",
            message=_ns(usage=_ns(input_tokens=12, output_tokens=0)),
        ),
        _ns(
            type="content_block_start",
            index=0,
            content_block=_ns(type="text"),
        ),
        _ns(type="content_block_delta", index=0, delta=_ns(type="text_delta", text="Hello, ")),
        _ns(type="content_block_delta", index=0, delta=_ns(type="text_delta", text="cyclist")),
        _ns(type="content_block_delta", index=0, delta=_ns(type="text_delta", text="!")),
        _ns(type="content_block_stop", index=0),
        _ns(
            type="message_delta",
            delta=_ns(stop_reason="end_turn"),
            usage=_ns(output_tokens=8),
        ),
    ]
    _set_fake_stream(events)

    out = _collect_sse_events(client, {"message": "Hi"})

    # Session preamble first so frontend can persist session_id before deltas.
    assert out[0]["type"] == "session"
    assert "session_id" in out[0]

    # Text deltas in order.
    deltas = [e for e in out if e["type"] == "text_delta"]
    assert [d["text"] for d in deltas] == ["Hello, ", "cyclist", "!"]

    # Exactly one iteration_end before the final done.
    iter_ends = [e for e in out if e["type"] == "iteration_end"]
    assert len(iter_ends) == 1
    assert iter_ends[0]["stop_reason"] == "end_turn"

    # Final done event carries token accounting.
    dones = [e for e in out if e["type"] == "done"]
    assert len(dones) == 1
    assert dones[0]["input_tokens"] == 12
    assert dones[0]["output_tokens"] == 8


def test_chat_stream_tool_use_emits_tool_use_complete_before_iteration_end(
    client: TestClient, seeded_db: None
) -> None:
    """A tool_use iteration should emit tool_use_start → tool_use_complete →
    tool_result (after dispatch) → iteration_end, in that order. The
    second iteration ships the final text."""
    import src.tools  # noqa: F401

    # First iter: ONE tool_use block (get_weather Amsterdam June) — fully assembled
    # input arrives via current_message_snapshot at content_block_stop time.
    iter1_snapshot = _ns(
        content=[
            _ns(
                type="tool_use",
                id="tu_w",
                name="get_weather",
                input={"location": "Amsterdam", "month": "June"},
            )
        ]
    )
    iter1_events: list[Any] = [
        _ns(type="message_start", message=_ns(usage=_ns(input_tokens=20, output_tokens=0))),
        _ns(
            type="content_block_start",
            index=0,
            content_block=_ns(type="tool_use", id="tu_w", name="get_weather"),
        ),
        _ns(type="content_block_stop", index=0),
        _ns(
            type="message_delta",
            delta=_ns(stop_reason="tool_use"),
            usage=_ns(output_tokens=30),
        ),
    ]
    # Second iter: final text wrap-up.
    iter2_events: list[Any] = [
        _ns(type="message_start", message=_ns(usage=_ns(input_tokens=60, output_tokens=0))),
        _ns(type="content_block_start", index=0, content_block=_ns(type="text")),
        _ns(type="content_block_delta", index=0, delta=_ns(type="text_delta", text="Mild and rainy.")),
        _ns(type="content_block_stop", index=0),
        _ns(
            type="message_delta",
            delta=_ns(stop_reason="end_turn"),
            usage=_ns(output_tokens=10),
        ),
    ]

    # The SDK exposes ``messages.stream(**kwargs)`` returning a fresh manager
    # per call. We thread two managers in sequence so iter1 → iter2 deliver
    # the right events.
    call_count = {"n": 0}

    def stream_factory(**_: Any) -> Any:
        if call_count["n"] == 0:
            call_count["n"] += 1
            return _FakeStreamManager(iter1_events, snapshot=iter1_snapshot)
        return _FakeStreamManager(iter2_events)

    fake = MagicMock()
    fake.messages = MagicMock()
    fake.messages.stream = stream_factory
    app.dependency_overrides[get_anthropic_client] = lambda: fake

    out = _collect_sse_events(client, {"message": "Weather in Amsterdam in June?"})
    event_types = [e["type"] for e in out]

    # Event-ordering contract per streaming.py:
    #   tool_use_start (block begins)
    #   tool_use_complete (input fully assembled)
    #   iteration_end (stop_reason="tool_use", emitted BEFORE dispatch — UI
    #                  shows "thinking… → calling tools" transition)
    #   tool_result (one per dispatched tool, AFTER iteration_end)
    #   iteration_end (next iter, stop_reason="end_turn")
    #   done (final summary)
    def first_idx(t: str) -> int:
        return next(i for i, e in enumerate(out) if e["type"] == t)

    iter_end_idxs = [i for i, e in enumerate(out) if e["type"] == "iteration_end"]
    tool_result_idxs = [i for i, e in enumerate(out) if e["type"] == "tool_result"]

    # tool_use lifecycle ordered within iter 1
    assert first_idx("tool_use_start") < first_idx("tool_use_complete")
    # tool_use_complete fires before iter 1's iteration_end
    assert first_idx("tool_use_complete") < iter_end_idxs[0]
    # tool_results land between the two iteration_end events
    assert iter_end_idxs[0] < tool_result_idxs[0] < iter_end_idxs[1]

    # Two iteration_end events (tool_use → end_turn).
    assert event_types.count("iteration_end") == 2
    # Done is the very last event.
    assert event_types[-1] == "done"


def test_chat_stream_error_during_stream_emits_typed_error_event(
    client: TestClient,
) -> None:
    """When ``messages.stream(...)`` raises (network drop, rate-limit, etc.)
    the endpoint should emit a structured ``error`` SSE event with a
    ``kind`` field, not crash the response stream. Validates the
    ``_classify_stream_error`` mapping is wired up."""
    from anthropic import APITimeoutError

    _set_fake_stream_raising(APITimeoutError(request=None))  # type: ignore[arg-type]

    out = _collect_sse_events(client, {"message": "Plan it"})
    errors = [e for e in out if e["type"] == "error"]
    assert len(errors) == 1
    err = errors[0]
    assert err["kind"] == "timeout"
    assert "took too long" in err["message"].lower()
