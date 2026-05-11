"""Agent loop tests with a mocked Anthropic client.

We never hit the real API in unit tests — that's what scripts/smoke_test.py
is for. These tests verify the loop's *control flow*: tool dispatch, message
threading, stop conditions, error handling, and trace accumulation.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.agent import ConversationState, run_turn
from src.agent.config import _clear_settings_cache

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Inject a fake API key so Settings doesn't fail to load in CI."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    _clear_settings_cache()
    yield
    _clear_settings_cache()


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
    """Build a MagicMock that mimics AsyncAnthropic.messages.create."""
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
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_tool_calls_returns_final_text() -> None:
    """If Claude returns end_turn immediately, the agent gives that text back."""
    client = make_fake_client(
        [
            FakeResponse(
                content=[FakeTextBlock(text="Hi! What route are you thinking of?")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=10, output_tokens=20),
            )
        ]
    )
    state = ConversationState()
    response = await run_turn(state, "Hi", client=client)

    assert response.iterations == 1
    assert response.message == "Hi! What route are you thinking of?"
    assert response.stop_reason == "end_turn"
    assert state.total_input_tokens == 10
    assert state.total_output_tokens == 20
    # State should now contain the user message + assistant message
    assert len(state.messages) == 2
    assert state.messages[0]["role"] == "user"
    assert state.messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_single_tool_call_dispatched_and_followed_up(seeded_db: None) -> None:
    """Claude asks for one tool, we dispatch it, Claude wraps up."""
    # Importing tools registers them so dispatch works
    import src.tools  # noqa: F401

    client = make_fake_client(
        [
            FakeResponse(
                content=[
                    FakeTextBlock(text="Let me check the route."),
                    FakeToolUseBlock(
                        id="tu_1",
                        name="get_route",
                        input={"start": "Amsterdam", "end": "Copenhagen"},
                    ),
                ],
                stop_reason="tool_use",
                usage=FakeUsage(input_tokens=50, output_tokens=80),
            ),
            FakeResponse(
                content=[FakeTextBlock(text="It's about 850km via Hamburg.")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=200, output_tokens=30),
            ),
        ]
    )
    state = ConversationState()
    response = await run_turn(state, "How far is it from Amsterdam to Copenhagen?", client=client)

    assert response.iterations == 2
    assert response.message == "It's about 850km via Hamburg."
    assert state.total_input_tokens == 250
    assert state.total_output_tokens == 110
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["name"] == "get_route"

    # Verify the message thread is well-formed for a Claude follow-up turn:
    # user → assistant(text+tool_use) → user(tool_result) → assistant(text)
    roles = [m["role"] for m in state.messages]
    assert roles == ["user", "assistant", "user", "assistant"]
    # The third message must contain a tool_result block matching the tool_use id
    third = state.messages[2]
    assert isinstance(third["content"], list)
    assert third["content"][0]["type"] == "tool_result"
    assert third["content"][0]["tool_use_id"] == "tu_1"


@pytest.mark.asyncio
async def test_parallel_tool_calls_in_one_turn_all_dispatched(seeded_db: None) -> None:
    """When Claude emits multiple tool_use blocks in one response, all run."""
    import src.tools  # noqa: F401

    client = make_fake_client(
        [
            FakeResponse(
                content=[
                    FakeToolUseBlock(
                        id="tu_a",
                        name="get_weather",
                        input={"location": "Amsterdam", "month": "June"},
                    ),
                    FakeToolUseBlock(
                        id="tu_b",
                        name="get_elevation_profile",
                        input={"start": "Amsterdam", "end": "Hoorn"},
                    ),
                ],
                stop_reason="tool_use",
                usage=FakeUsage(input_tokens=100, output_tokens=60),
            ),
            FakeResponse(
                content=[FakeTextBlock(text="Cool route.")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=300, output_tokens=10),
            ),
        ]
    )
    state = ConversationState()
    await run_turn(state, "Plan day 1", client=client)

    # Both tool_results should be in the user message we sent back
    user_after_tools = state.messages[2]
    blocks = user_after_tools["content"]
    assert len(blocks) == 2
    ids = {b["tool_use_id"] for b in blocks}
    assert ids == {"tu_a", "tu_b"}


@pytest.mark.asyncio
async def test_tool_dispatch_error_marked_is_error_true() -> None:
    """An invalid tool call yields a tool_result with is_error=True for Claude to recover."""
    import src.tools  # noqa: F401

    client = make_fake_client(
        [
            FakeResponse(
                content=[
                    FakeToolUseBlock(
                        id="tu_bad",
                        name="get_weather",
                        input={"location": "X", "month": "Smarch"},  # invalid month
                    )
                ],
                stop_reason="tool_use",
                usage=FakeUsage(input_tokens=50, output_tokens=20),
            ),
            FakeResponse(
                content=[FakeTextBlock(text="My bad — what month did you say?")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=80, output_tokens=12),
            ),
        ]
    )
    state = ConversationState()
    await run_turn(state, "Weather please", client=client)

    blocks = state.messages[2]["content"]
    assert blocks[0]["is_error"] is True


@pytest.mark.asyncio
async def test_trace_records_every_event(seeded_db: None) -> None:
    """The trace is the data behind /trace — must capture user → tool → result → stop."""
    import src.tools  # noqa: F401

    client = make_fake_client(
        [
            FakeResponse(
                content=[
                    FakeTextBlock(text="planning..."),
                    FakeToolUseBlock(
                        id="tu_r",
                        name="get_route",
                        input={"start": "Amsterdam", "end": "Copenhagen"},
                    ),
                ],
                stop_reason="tool_use",
                usage=FakeUsage(input_tokens=10, output_tokens=10),
            ),
            FakeResponse(
                content=[FakeTextBlock(text="done")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=10, output_tokens=10),
            ),
        ]
    )
    state = ConversationState()
    await run_turn(state, "go", client=client)

    types = [e.type for e in state.trace]
    assert types[0] == "user_message"
    assert "assistant_text" in types
    assert "tool_use" in types
    assert "tool_result" in types
    assert types[-1] == "stop"


@pytest.mark.asyncio
async def test_state_is_resumable_across_turns() -> None:
    """Calling run_turn twice should accumulate, not reset."""
    import src.tools  # noqa: F401

    client = make_fake_client(
        [
            FakeResponse(
                content=[FakeTextBlock(text="What's your daily km target?")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=20, output_tokens=10),
            ),
            FakeResponse(
                content=[FakeTextBlock(text="OK, planning for 100km/day.")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=40, output_tokens=15),
            ),
        ]
    )
    state = ConversationState()
    await run_turn(state, "Plan a trip", client=client)
    await run_turn(state, "100km a day", client=client)

    assert state.total_turns == 2
    # 2 user msgs + 2 assistant msgs = 4
    assert len(state.messages) == 4
    assert state.total_input_tokens == 60
    assert state.total_output_tokens == 25


@pytest.mark.asyncio
async def test_loop_safety_net_raises_after_max_iterations(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pathological tool-only loop should be capped, not run forever."""
    import src.tools  # noqa: F401

    monkeypatch.setenv("MAX_LOOP_ITERATIONS", "3")
    _clear_settings_cache()

    # Always returns tool_use — never converges
    def make_loop_response() -> FakeResponse:
        return FakeResponse(
            content=[
                FakeToolUseBlock(
                    id="tu_x",
                    name="get_weather",
                    input={"location": "Amsterdam", "month": "June"},
                )
            ],
            stop_reason="tool_use",
            usage=FakeUsage(input_tokens=5, output_tokens=5),
        )

    client = make_fake_client([make_loop_response() for _ in range(10)])
    state = ConversationState()

    from src.agent import AgentLoopExceeded

    with pytest.raises(AgentLoopExceeded):
        await run_turn(state, "loop", client=client)


# ---------------------------------------------------------------------------
# Prompt-following guardrail — Phase 1.13 (post-hoc critique_trip_plan check)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guardrail_fires_when_plan_shipped_without_critique() -> None:
    """If Claude ships a plan-shaped response with no critique_trip_plan
    call this turn, the orchestrator MUST nudge it to comply rather than
    let the contract violation slip through. The guardrail injects a
    synthetic user message and loops once more."""
    import src.tools  # noqa: F401

    plan_text = (
        "Here is your plan:\n\n"
        "## Day 1 — Amsterdam → Hoorn\n"
        "- Distance: 40 km · Elevation: +20 m\n\n"
        "## Day 2 — Hoorn → Enkhuizen\n"
        "- Distance: 28 km · Elevation: +15 m\n"
    )
    revised_text = (
        "Got it — I'll run the critique first.\n\n"
        "## Day 1 — Amsterdam → Hoorn\n"
        "- Distance: 40 km · Elevation: +20 m\n\n"
        "## Day 2 — Hoorn → Enkhuizen\n"
        "- Distance: 28 km · Elevation: +15 m\n"
    )

    client = make_fake_client(
        [
            # Iter 1 — Claude ships a plan with NO critique call. Guardrail fires.
            FakeResponse(
                content=[FakeTextBlock(text=plan_text)],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=100, output_tokens=80),
            ),
            # Iter 2 — Claude complies and calls critique_trip_plan.
            FakeResponse(
                content=[
                    FakeToolUseBlock(
                        id="tu_critique",
                        name="critique_trip_plan",
                        input={
                            "days": [
                                {"day_number": 1, "distance_km": 40.0},
                                {"day_number": 2, "distance_km": 28.0},
                            ],
                            "daily_km_target": 40.0,
                        },
                    )
                ],
                stop_reason="tool_use",
                usage=FakeUsage(input_tokens=50, output_tokens=40),
            ),
            # Iter 3 — final plan after critique.
            FakeResponse(
                content=[FakeTextBlock(text=revised_text)],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=80, output_tokens=80),
            ),
        ]
    )
    state = ConversationState()
    response = await run_turn(state, "Plan it", client=client)

    # 3 iterations: original draft + nudge-driven critique call + final ship.
    assert response.iterations == 3
    # Final text is from the third response, after critique ran.
    assert "## Day 1" in response.message
    # The trace contains the guardrail marker so observability shows the nudge.
    guardrail_events = [
        e for e in state.trace
        if e.type == "tool_use" and e.payload.get("name") == "_guardrail_critique_missing"
    ]
    assert len(guardrail_events) == 1, "guardrail should fire exactly once"
    # And critique_trip_plan ran on iteration 2 (post-nudge).
    critique_events = [
        e for e in state.trace
        if e.type == "tool_use" and e.payload.get("name") == "critique_trip_plan"
    ]
    assert len(critique_events) == 1


@pytest.mark.asyncio
async def test_guardrail_silent_when_critique_already_called(seeded_db: None) -> None:
    """If Claude calls critique_trip_plan before presenting the plan, the
    guardrail must NOT fire — the contract was honoured."""
    import src.tools  # noqa: F401

    plan_text = (
        "Plan complete:\n\n"
        "## Day 1 — Amsterdam → Hoorn\n"
        "- Distance: 40 km\n\n"
        "## Day 2 — Hoorn → Enkhuizen\n"
        "- Distance: 28 km\n"
    )

    client = make_fake_client(
        [
            # Iter 1 — Claude calls critique_trip_plan FIRST.
            FakeResponse(
                content=[
                    FakeToolUseBlock(
                        id="tu_critique",
                        name="critique_trip_plan",
                        input={
                            "days": [
                                {"day_number": 1, "distance_km": 40.0},
                                {"day_number": 2, "distance_km": 28.0},
                            ],
                            "daily_km_target": 40.0,
                        },
                    )
                ],
                stop_reason="tool_use",
                usage=FakeUsage(input_tokens=50, output_tokens=40),
            ),
            # Iter 2 — Claude ships the plan (guardrail must stay silent).
            FakeResponse(
                content=[FakeTextBlock(text=plan_text)],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=80, output_tokens=80),
            ),
        ]
    )
    state = ConversationState()
    response = await run_turn(state, "Plan it", client=client)

    # 2 iterations only — no guardrail-induced extra loop.
    assert response.iterations == 2
    guardrail_events = [
        e for e in state.trace
        if e.type == "tool_use" and e.payload.get("name") == "_guardrail_critique_missing"
    ]
    assert guardrail_events == [], "guardrail should NOT fire when critique was called"


@pytest.mark.asyncio
async def test_guardrail_silent_for_non_plan_responses() -> None:
    """A clarifying question or short answer is not a plan presentation —
    no Day-N markers, so the guardrail must stay silent even with no critique."""
    client = make_fake_client(
        [
            FakeResponse(
                content=[
                    FakeTextBlock(text="What month are you planning to travel?")
                ],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=10, output_tokens=15),
            )
        ]
    )
    state = ConversationState()
    response = await run_turn(state, "Plan a trip", client=client)

    assert response.iterations == 1
    assert "month" in response.message.lower()
    guardrail_events = [
        e for e in state.trace
        if e.type == "tool_use" and e.payload.get("name") == "_guardrail_critique_missing"
    ]
    assert guardrail_events == []


@pytest.mark.asyncio
async def test_guardrail_fires_at_most_once_per_turn() -> None:
    """If Claude ignores the nudge and ships another plan-shaped response
    without calling critique, we DO NOT loop forever — the guardrail's
    one-shot flag prevents amplification. The plan ships with a warning
    in the log; the outer eval suite catches systemic violations."""
    plan_text = (
        "Plan:\n\n## Day 1 — A → B\n- 50 km\n\n## Day 2 — B → C\n- 50 km\n"
    )

    client = make_fake_client(
        [
            # Iter 1 — plan with no critique. Guardrail fires.
            FakeResponse(
                content=[FakeTextBlock(text=plan_text)],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=80, output_tokens=80),
            ),
            # Iter 2 — Claude ignores the nudge and ships the plan again.
            # Guardrail must NOT fire again, so this is the final iteration.
            FakeResponse(
                content=[FakeTextBlock(text=plan_text + "\n(unchanged)")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=70, output_tokens=80),
            ),
        ]
    )
    state = ConversationState()
    response = await run_turn(state, "Plan it", client=client)

    assert response.iterations == 2
    assert "unchanged" in response.message
    # Only ONE guardrail event in the trace — second violation logged but
    # not nudged.
    guardrail_events = [
        e for e in state.trace
        if e.type == "tool_use" and e.payload.get("name") == "_guardrail_critique_missing"
    ]
    assert len(guardrail_events) == 1
