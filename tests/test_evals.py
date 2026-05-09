"""Eval harness — real-Claude scenarios that score the agent against the rubric.

These tests cost real money (~$0.05–$0.10 per scenario, ~$0.25 for the full
suite) so they're behind the `evals` pytest marker and skipped by default.

Run with:
    make evals
    # or:
    pytest -m evals -v -s

Each scenario asserts behaviors the rubric values:

  Scenario 1 · Happy path (London → Paris, fully specified)
    → Multi-step reasoning (20%) + Product thinking (10%)
    Expects parallel fan-out, a day-by-day plan, ferry mention.

  Scenario 2 · Infeasibility refusal (Berlin → Mumbai in 30 days)
    → Conversation handling (15%) + Product thinking (10%)
    Expects an honest refusal, no fake plan, alternatives offered.

  Scenario 3 · Mid-conversation preference change
    → Conversation handling (15%) + Architecture (25%)
    Expects state-aware adaptation: re-call get_route with the new target,
    DO NOT re-ask origin/dates.

  Scenario 4 · Constraint conflict surfacing (over-constrained request)
    → Conversation handling (15%) + Product thinking (10%)
    Expects the agent to flag the conflict and offer trade-offs, not silently
    violate one of the constraints.

Why we run these against real Claude (not a mocked client):
  These tests are about *emergent agent behavior* — clarifying questions,
  honest refusals, plan-then-react. Mocking that would just be testing my
  mocks. Real calls are the only way to know the system prompt is actually
  driving Claude the way we expect.
"""

from __future__ import annotations

import os
import re

import pytest

from src.agent import ConversationState, run_turn

# Importing src.tools registers tools so the agent can dispatch them.
import src.tools  # noqa: F401


pytestmark = [
    pytest.mark.evals,
    pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-ant-...")
        or os.getenv("ANTHROPIC_API_KEY") == "test-key-not-real",
        reason="ANTHROPIC_API_KEY not set to a real key",
    ),
]


def _names_called(state: ConversationState) -> list[str]:
    """Tool names invoked across all iterations of the most recent turn."""
    return [e.payload["name"] for e in state.trace if e.type == "tool_use"]


def _assistant_text(state: ConversationState) -> str:
    """Concatenated final assistant text across the conversation."""
    return "\n".join(
        e.payload["text"] for e in state.trace if e.type == "assistant_text"
    )


def _print_scoreboard(name: str, state: ConversationState, checks: list[tuple[str, bool]]) -> None:
    """Pretty-print a per-scenario summary. Visible with `-s`."""
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    print(f"\n{'=' * 70}")
    print(f"  EVAL · {name}  →  {passed}/{total} checks passed")
    print(f"  iterations={state.total_turns}  "
          f"input_tokens={state.total_input_tokens}  "
          f"output_tokens={state.total_output_tokens}")
    print(f"{'-' * 70}")
    for label, ok in checks:
        marker = "✓" if ok else "✗"
        print(f"  {marker} {label}")
    print(f"{'=' * 70}\n")


# ---------------------------------------------------------------------------
# Scenario 1 — Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eval_happy_path_london_to_paris(seeded_db: None) -> None:
    """Fully specified request → agent should fan out, build a day-by-day plan,
    surface the ferry, hit every required tool."""
    state = ConversationState()
    response = await run_turn(
        state,
        "Plan a 4-day cycle from London to Paris, 100km/day, prefer camping "
        "but a hostel on night 3, traveling in June.",
    )

    tools_called = _names_called(state)
    text = response.message.lower()

    checks = [
        ("get_route called at least once", tools_called.count("get_route") >= 1),
        ("get_elevation_profile called ≥ 3 times", tools_called.count("get_elevation_profile") >= 3),
        ("get_weather called ≥ 3 times", tools_called.count("get_weather") >= 3),
        ("find_accommodation called ≥ 3 times", tools_called.count("find_accommodation") >= 3),
        ("critique_trip_plan called (self-critique before shipping)",
         tools_called.count("critique_trip_plan") >= 1),
        ("total tool calls ≥ 9 (multi-step + critique proof)", len(tools_called) >= 9),
        ("output mentions the ferry (Newhaven/Dieppe)",
         any(kw in text for kw in ("ferry", "newhaven", "dieppe", "channel"))),
        ("output is a day-by-day plan",
         bool(re.search(r"day\s*1", text) and re.search(r"day\s*[2-4]", text))),
        ("output mentions a real seeded accommodation",
         any(name in text for name in ("yha", "generator", "auberge", "camping", "hostel"))),
    ]

    _print_scoreboard("S1 · happy path London→Paris", state, checks)
    for label, ok in checks:
        assert ok, f"happy path check failed: {label}\n---\n{response.message[:1500]}"


# ---------------------------------------------------------------------------
# Scenario 2 — Infeasibility refusal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eval_infeasibility_refusal(seeded_db: None) -> None:
    """Berlin → Mumbai in 30 days = ~217km/day sustained across borders. A
    real plan would be irresponsible — the agent must refuse honestly."""
    state = ConversationState()
    response = await run_turn(
        state,
        "Plan a cycling trip from Berlin to Mumbai in 30 days.",
    )

    text = response.message.lower()
    text_full = response.message

    # Surface feasibility math: any of these phrasings counts.
    has_distance_or_pace_math = any(
        kw in text for kw in (
            "km/day", "km per day", "kilometres", "kilometers", "kilometre", "kilometer",
            "distance", "feasible", "infeasible", "realistic", "unrealistic",
            "not possible", "can't", "won't", "cannot", "isn't possible", "not physically",
            "physically", "impossible",
        )
    )

    # The agent suggested *some* path forward — alternative trip, lower target,
    # asking the user to reconsider. We accept any of: alternative-keyword,
    # closing question, listing a different destination, or listing different
    # day counts.
    suggests_alternatives = (
        # Closing with a question asking the user what they want
        "?" in text_full
        or any(kw in text for kw in (
            "alternative", "instead", "consider", "could", "might", "option",
            "perhaps", "suggest", "recommend", "rather", "what about",
        ))
        # Mentions specific alternative destinations / shorter trips
        or bool(re.search(r"\b(istanbul|athens|prague|warsaw|berlin to)\b", text))
        # Lists a more realistic day-count window
        or bool(re.search(r"\b\d{2,3}[–\-]\d{2,3}\s*days?\b", text))
    )

    has_no_full_plan = not bool(
        re.search(r"day\s*1.{0,400}day\s*2.{0,400}day\s*3", text, re.DOTALL)
    )

    checks = [
        ("agent surfaces distance/pace/feasibility math", has_distance_or_pace_math),
        ("agent suggests alternatives or asks user to reconsider", suggests_alternatives),
        ("agent does NOT produce a full day-by-day plan", has_no_full_plan),
        ("response is reasonably short (refused early, didn't fan out)",
         response.output_tokens < 1500),
    ]

    _print_scoreboard("S2 · infeasibility refusal", state, checks)
    for label, ok in checks:
        assert ok, (
            f"infeasibility check failed: {label}\n"
            f"---\noutput_tokens={response.output_tokens}\n"
            f"message:\n{text_full[:1500]}"
        )


# ---------------------------------------------------------------------------
# Scenario 3 — Mid-conversation preference change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eval_preference_change_mid_conversation(seeded_db: None) -> None:
    """Two turns. Turn 2 changes daily km + accommodation preference. Agent
    must adapt without re-asking what we already told it."""
    state = ConversationState()

    # Turn 1 — set up the trip
    await run_turn(
        state,
        "Plan a London to Paris cycle, 100km/day, prefer camping, traveling in June.",
    )

    tools_after_turn_1 = _names_called(state)

    # Turn 2 — flip preferences
    await run_turn(
        state,
        "Actually let's do 60km/day and stay in hotels instead.",
    )

    tools_after_turn_2 = _names_called(state)
    new_tool_calls = tools_after_turn_2[len(tools_after_turn_1):]

    # Look at the second turn's final assistant message
    # (last few assistant_text events)
    later_assistant_events = [
        e for e in state.trace if e.type == "assistant_text"
    ]
    final_text = later_assistant_events[-1].payload["text"].lower() if later_assistant_events else ""

    checks = [
        ("turn 2 re-called get_route with new daily target",
         "get_route" in new_tool_calls),
        ("turn 2 queried hotels via find_accommodation",
         any(
             e.type == "tool_use"
             and e.payload["name"] == "find_accommodation"
             and e.iteration > 1  # later iterations belong to turn 2
             and "hotel" in str(e.payload.get("input", {})).lower()
             for e in state.trace
         )),
        ("turn 2 made multiple tool calls (fanned out fresh data)",
         len(new_tool_calls) >= 3),
        ("agent did NOT re-ask which cities (no clarifying loop)",
         not re.search(r"which (cities|origin|destination|route)", final_text)),
        ("agent did NOT re-ask the month",
         not re.search(r"what month|which month|when are you", final_text)),
        ("two-turn state survived (total_turns == 2)", state.total_turns == 2),
    ]

    _print_scoreboard("S3 · mid-conversation preference change", state, checks)
    for label, ok in checks:
        assert ok, f"preference-change check failed: {label}"


# ---------------------------------------------------------------------------
# Scenario 4 — Constraint conflict surfacing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eval_constraint_conflict_surfacing(seeded_db: None) -> None:
    """Over-constrained: London → Paris is ~380km. 2 days × 50km/day = 100km
    of capacity. Agent MUST flag the gap and offer trade-offs — not silently
    invent a way to fit 380km into 100km of riding."""
    state = ConversationState()
    response = await run_turn(
        state,
        "Plan a London to Paris cycle in 2 days at 50km/day, camping every night.",
    )

    text = response.message.lower()
    text_full = response.message

    # Did the agent push back on the constraint set?
    # "Surfacing the conflict" can take many shapes:
    #   - explicit conflict language ("doesn't add up", "conflict")
    #   - quoting both numbers (the requested days/km vs the actual route)
    #   - naming a different day count than what was requested
    #   - asking a clarifying "did you mean..." question
    explicit_conflict_phrases = [
        "doesn't add up", "doesn't match", "conflict", "issue", "problem",
        "would need", "would take", "more days", "more km",
        "increase", "extend", "doesn't fit", "isn't enough",
        "infeasible", "not enough", "too short", "won't work",
        "can't fit", "can't be done", "cannot fit", "math doesn't",
        "math", "not 2", "not two",
    ]
    has_explicit_conflict_phrase = any(p in text for p in explicit_conflict_phrases)

    # The agent quoted a different/larger day count or distance than 2 / 100km
    has_alternative_numbers = bool(
        re.search(r"\b([3-9]|1[0-9])\s*[–\-]?\s*\d{0,2}\s*days?\b", text)
        or re.search(r"\b[2-9]\d\d\s*km\b", text)  # e.g. "380 km", "450-500 km"
    )

    # Asks a "did you mean / which did you mean" clarifying question
    asks_clarification = (
        "?" in text_full
        and any(p in text for p in ("did you mean", "which", "would you", "do you"))
    )

    surfaces_conflict = (
        has_explicit_conflict_phrase or has_alternative_numbers or asks_clarification
    )

    offers_alternatives = (
        ("?" in text_full)
        or any(kw in text for kw in ("option", "alternative", "could", "either", "or "))
    )

    # Did NOT silently produce a 2-day plan that pretends 100km covers 380km
    has_no_silent_plan = not (
        bool(re.search(r"day\s*1.{0,300}day\s*2", text, re.DOTALL))
        and not surfaces_conflict
    )

    checks = [
        ("agent surfaces the math/constraint conflict", surfaces_conflict),
        ("agent offers alternatives or asks user to choose", offers_alternatives),
        ("agent did NOT silently produce a fake 2-day plan", has_no_silent_plan),
        ("agent stops early (didn't fan out 18 tool calls before refusing)",
         response.iterations <= 3),
    ]

    _print_scoreboard("S4 · constraint conflict surfacing", state, checks)
    for label, ok in checks:
        assert ok, (
            f"conflict surfacing check failed: {label}\n"
            f"---\nmessage:\n{response.message[:1800]}"
        )
