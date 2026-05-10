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


# ---------------------------------------------------------------------------
# Scenario 7 — Silent constraint relaxation transparency
# ---------------------------------------------------------------------------
#
# Surfaced 2026-05-10 by Gemini fact-check on a real session:
#
#   User: "Plan a 4-day London → Paris on the V16a, 100km/day, ..."
#   Agent: <produces plan with two 109km days>
#   User: "Day 4 feels brutal — can you offer alternatives?"
#   Agent: "Sure! Option A: 5 days, 73 km/day. Option B: 4 days, rebalanced."
#
# Option A silently dropped the user's 100 km/day target by 27% without
# flagging it. The user reading carelessly would think their target was
# honored. This is the SOFT end of the S2 (infeasibility refusal)
# spectrum — same honesty principle, different failure mode.
#
# The rubric: every alternative the agent offers must explicitly name
# which user-stated constraint it relaxes (km/day target, day count,
# accommodation pattern). When alternatives DON'T relax any constraint,
# they should explicitly say so — otherwise the agent can game the
# rubric by always claiming a relaxation.


@pytest.mark.asyncio
async def test_eval_silent_constraint_relaxation_transparency(seeded_db: None) -> None:
    """S7 · When the agent offers alternatives in response to a constraint
    pushback, every alternative must explicitly name what it relaxes —
    or explicitly state that all constraints are honored. No silent drops.

    Two turns:
      1. Standard 4-day London → Paris @ 100 km/day plan via V16a.
         Will produce two ~109 km days on the V16a corridor.
      2. User pushes back on Day 4's 109 km. Agent offers alternatives.
         For each alternative that changes the day count or daily km
         target, the agent MUST acknowledge the change. For alternatives
         that don't change either, the agent MUST say so explicitly.
    """
    state = ConversationState()

    # Turn 1 — set up the canonical plan
    await run_turn(
        state,
        "Plan a 4-day cycle from London to Paris on the Avenue Verte, "
        "100km/day, prefer camping but a hostel every 3rd night, traveling "
        "in June. Use the V16a Beauvais variant.",
    )

    # Turn 2 — push the constraint conflict; force alternative-offering
    response = await run_turn(
        state,
        "Day 4 at 109km after the 108km ferry day on Day 2 feels brutal. "
        "Can you offer a couple of alternatives that ease this for a "
        "first multi-day trip?",
    )

    text = response.message.lower()

    # ── Did the agent offer multiple alternatives? ──────────────────────
    offers_alternatives = (
        any(
            kw in text
            for kw in (
                "option a", "option b", "option 1", "option 2",
                "first option", "second option", "alternative a",
                "alternative b", "two options", "three options",
                "here are", "here's", "couple of",
            )
        )
        or text.count("\n* ") >= 2
        or text.count("\n- ") >= 2
        or bool(re.search(r"\n\d\.\s", response.message))
    )

    # ── Did the agent propose a different day count than 4? ─────────────
    proposes_more_days = (
        bool(re.search(r"\b[5-9]\s*[\-–]?\s*days?\b", text))
        or "five days" in text
        or "five-day" in text
        or "six days" in text
        or "six-day" in text
        or bool(re.search(r"\b[5-9]\s*-day\b", text))
    )

    # ── Did the agent propose a daily km figure noticeably below 100? ───
    # Look for explicit lower-target language. We're permissive here: the
    # agent might say "73 km/day", "averaging 80 km/day", "drops to 75 km",
    # etc. The check is for ANY mention of a daily km figure under 95
    # alongside any "per day" framing.
    lower_km_match = re.search(
        r"\b([5-9]\d|7\d|8\d|9[0-4])\s*(?:km|kilometer)s?\s*(?:[/\-]|\bper\b|\ba\s)\s*day",
        text,
    )
    proposes_lower_km = bool(lower_km_match) or any(
        p in text
        for p in (
            "below 100", "under 100", "less than 100",
            "drops to 7", "drops to 8",
            "averaging 7", "averaging 8",
            "reduce to 8", "reduces to 8",
            "reduces to 7", "reduce to 7",
        )
    )

    # ── Acknowledgment language: agent named the relaxation ─────────────
    relaxation_language = any(
        p in text
        for p in (
            "extends to", "extending to", "extending the trip",
            "stretches to", "stretches the trip",
            "instead of 4", "instead of four", "rather than 4",
            "rather than four",
            "from 4 days", "from four days",
            "from 100", "vs your 100", "vs 100 km",
            "below your 100", "below your target", "below your stated",
            "drops below", "lower than your", "less than your",
            "your 4-day", "your 4 day", "your four-day",
            "relaxes", "relaxing", "relaxed",
            "this changes", "this drops", "this extends",
            "trade-off", "trade off",
        )
    )

    # If agent proposed a different day count → must acknowledge it
    if proposes_more_days:
        names_day_count_change = (
            relaxation_language
            or "4-day" in text
            or "4 day" in text
            or bool(re.search(r"\b4\s*[\-–]?\s*days?\b", text))
        )
    else:
        names_day_count_change = True  # no change, vacuously satisfied

    # If agent proposed lower daily km → must acknowledge it
    if proposes_lower_km:
        names_km_change = (
            relaxation_language
            or "100 km" in text
            or "100km" in text
            or "your target" in text
            or "your stated" in text
        )
    else:
        names_km_change = True  # no change, vacuously satisfied

    # If neither constraint was changed → agent should explicitly say so
    no_relaxation = not proposes_more_days and not proposes_lower_km
    if no_relaxation:
        keeps_constraints_explicit = any(
            p in text
            for p in (
                "keeps your 4", "honors your 4", "keep your 4",
                "keeps your 100", "honors your 100", "keep your 100",
                "stays within", "still 4 days", "still at 100",
                "no change to", "rebalances", "rebalancing",
                "redistributes", "redistribute", "shifts the load",
                "without extending", "without dropping",
                "honor all", "honors all", "honoring all",
                "all your constraints", "all of your constraints",
            )
        )
    else:
        keeps_constraints_explicit = True

    checks = [
        ("agent offered multiple alternatives in response to pushback",
         offers_alternatives),
        ("alternatives that change day count name the relaxation explicitly",
         names_day_count_change),
        ("alternatives that lower daily km name the relaxation explicitly",
         names_km_change),
        ("alternatives that honor all constraints say so explicitly",
         keeps_constraints_explicit),
    ]

    _print_scoreboard(
        "S7 · silent constraint relaxation transparency", state, checks
    )
    for label, ok in checks:
        assert ok, (
            f"silent-relaxation check failed: {label}\n"
            f"---\nmessage:\n{response.message[:2200]}"
        )


# ---------------------------------------------------------------------------
# Scenario 8 — June session regression (the bug-list from 2026-05-10)
# ---------------------------------------------------------------------------
#
# Real user session that surfaced the agent's 188 km hallucination, the
# silent weather drop, missing distance/elevation lines, and unreliable
# accommodation type tagging. This scenario replays the full 4-turn
# sequence and asserts each fix holds.
#
# What it locks in:
#   1. Distance + Elevation on every day (parser regression, header math)
#   2. Stay: (type) tag on every accommodation (UI glyph)
#   3. No day past the 150 km absolute ceiling — critique must block
#   4. Weather present in the response when the user supplied dates
#   5. critique_trip_plan called on every plan + every re-plan
#   6. Prose numbers match the structured day list (no 117 vs 188)


def _every_day_has_distance_and_elevation(text: str) -> tuple[bool, list[str]]:
    """Walk the markdown, find Day-N sections, check each has both lines."""
    sections = re.split(r"(?:^|\n)#{0,3}\s*Day\s+\d+", text)[1:]
    misses: list[str] = []
    for i, section in enumerate(sections, 1):
        section_lower = section.lower()
        has_dist = bool(re.search(r"distance\s*[:\-]?\s*\d", section_lower))
        has_elev = bool(re.search(r"elevation\s*[:\-]?\s*[+]?\d", section_lower))
        if not (has_dist and has_elev):
            misses.append(
                f"Day {i}: distance={has_dist}, elevation={has_elev}"
            )
    return (not misses, misses)


def _every_stay_line_has_type_tag(text: str) -> tuple[bool, list[str]]:
    """Each accommodation listing must carry a `(type)` tag.

    Accepts both `Stay: Foo (type)` and `**Night N — Location**` followed
    by `- Foo (type)` on the next bullet — the agent uses both shapes.
    """
    # `Stay:` lines
    stay_lines = re.findall(
        r"(?im)^\s*[*\-]?\s*\*{0,2}\s*Stay\s*[:\-].*$", text
    )
    # `**Night N — Location**` + next bulleted line is the accommodation
    night_blocks = re.findall(
        r"(?im)^\s*\*{0,2}\s*(?:Night|Day)\s+\d+\b.*?\n\s*[*\-]\s+([^\n]+)",
        text,
    )
    candidates = stay_lines + night_blocks
    misses: list[str] = []
    type_re = re.compile(
        r"\((?:camping|hostel|hotel|guest\s*house|guesthouse|ferry|cabin|onboard)",
        re.IGNORECASE,
    )
    for line in candidates:
        # Skip obvious header-only lines that don't actually name accommodation
        if not re.search(r"[a-z]{4,}", line):
            continue
        if not type_re.search(line):
            misses.append(line.strip()[:120])
    return (not misses, misses)


def _count_accommodation_listings(text: str) -> int:
    """Count distinct accommodation type tags in the response.

    Each accommodation is required to carry a `(type, ...)` tag — see
    the prompt rule. Counting the tags is more robust than parsing the
    surrounding markdown shape (the agent uses Stay:/Night N/numbered
    list interchangeably).
    """
    tag_re = re.compile(
        r"\((?:camping|hostel|hotel|guest\s*house|guesthouse|ferry|cabin|onboard)\b",
        re.IGNORECASE,
    )
    return len(tag_re.findall(text))


def _max_day_distance_km(text: str) -> int | None:
    """Largest km figure found on a Day-section Distance line."""
    sections = re.split(r"(?:^|\n)#{0,3}\s*Day\s+\d+", text)[1:]
    kms: list[int] = []
    for section in sections:
        m = re.search(r"distance\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*km", section, re.IGNORECASE)
        if m:
            kms.append(int(float(m.group(1))))
    return max(kms) if kms else None


@pytest.mark.asyncio
async def test_eval_june_session_regression(seeded_db: None) -> None:
    """Full replay of the 2026-05-10 user session that surfaced the bug list.

    Four turns:
      1. Plan a 4-day cycle London→Paris on V16a, 100km/day, June.
      2. (no user input — turn 1 already names V16a)
      3. "Day 2 and 4 feel like a stretch — can we do this in 5 days?"
      4. "Day 3 sounds good, where should I stay each day and what's the
         weather like if I travel between 10-14 June?"
    """
    state = ConversationState()

    # Turn 1 — the canonical plan request, naming V16a so we skip the
    # variant comparison step (faster + the bugs were all post-comparison).
    r1 = await run_turn(
        state,
        "Plan a 4-day cycle from London to Paris on the V16a Beauvais "
        "variant, 100km/day, prefer camping and hostels, traveling in June.",
    )

    # Turn 2 — push back on long days, ask for 5 days
    r2 = await run_turn(
        state,
        "Day 2 and Day 4 feel like a stretch for me — what if we did this "
        "in 5 days instead?",
    )

    # Turn 3 — accept rebalanced plan + ask for weather + accommodations
    # for specific dates. The CRITICAL question — checks weather isn't
    # silently dropped.
    r3 = await run_turn(
        state,
        "Sounds good. Where would I stay each night, and what's the weather "
        "typically like if I plan to travel between 10-14 June?",
    )

    tools_called = _names_called(state)
    # Concatenate every assistant message so we check structure across
    # all three responses — bugs in any turn count.
    all_text = "\n\n".join(
        e.payload["text"] for e in state.trace if e.type == "assistant_text"
    )
    final_text = r3.message
    final_lower = final_text.lower()

    # ── Structure assertions ─────────────────────────────────────────────
    dist_elev_ok, dist_elev_misses = _every_day_has_distance_and_elevation(final_text)
    stay_tag_ok, stay_tag_misses = _every_stay_line_has_type_tag(final_text)
    max_km = _max_day_distance_km(final_text)

    # ── Critique was called on every plan-producing turn ────────────────
    critique_calls = tools_called.count("critique_trip_plan")

    # ── Weather surfaced in the final turn ──────────────────────────────
    weather_mentioned = any(
        kw in final_lower
        for kw in (
            "weather", "°c", "rain", "temperature", "forecast",
            "june climate", "june temp", "june weather", "rainfall",
        )
    )

    # ── No leading "My take" framing on plan choices ────────────────────
    # We don't ban operational advice like "I'd recommend booking ahead" —
    # that's actionable, not editorialising. We only flag framing that
    # picks an option/plan on the user's behalf without being asked.
    leading_framing = bool(
        re.search(
            r"\b(my take\s*[:\-]|my recommendation\s*[:\-]|"
            r"i(?:'d| would)? recommend (?:option|plan|going with|the \d|alternative\s+[ab])|"
            r"my pick (?:is|would be))",
            final_lower,
        )
    )

    # ── At least one accommodation per day in the final plan ────────────
    accom_listing_count = _count_accommodation_listings(final_text)

    checks = [
        ("every day has BOTH Distance and Elevation lines",
         dist_elev_ok),
        ("every Stay: line has a (type) tag",
         stay_tag_ok),
        ("no day exceeds the 150 km absolute ceiling",
         max_km is None or max_km <= 150),
        ("get_weather called when user asked about June 10-14",
         tools_called.count("get_weather") >= 2),
        ("response surfaces weather for the requested dates",
         weather_mentioned),
        ("critique_trip_plan called on every plan-producing turn (≥2 times)",
         critique_calls >= 2),
        ("agent did NOT lead with 'My take:' framing",
         not leading_framing),
        ("final plan lists ≥3 nightly accommodations (Stay: or Night N)",
         accom_listing_count >= 3),
        ("final response is a substantive plan, not a question",
         len(final_text) > 600),
    ]

    _print_scoreboard("S8 · June session regression", state, checks)

    # Detailed misses surface in the assertion message so a failure is
    # immediately actionable.
    detail_lines = []
    if not dist_elev_ok:
        detail_lines.append(f"Distance/Elevation gaps: {dist_elev_misses}")
    if not stay_tag_ok:
        detail_lines.append(f"Stay-tag misses: {stay_tag_misses}")
    if max_km is not None and max_km > 150:
        detail_lines.append(f"Max day distance: {max_km} km (ceiling is 150)")

    for label, ok in checks:
        assert ok, (
            f"June regression check failed: {label}\n"
            + ("\n".join(detail_lines) + "\n---\n" if detail_lines else "")
            + f"turn-3 message ({len(r3.message)} chars):\n{r3.message[:2500]}"
        )

    # Quietly note the multi-turn token spend so the user can see what
    # this scenario actually costs to run.
    print(
        f"  [S8] tokens this run: in={r1.input_tokens + r2.input_tokens + r3.input_tokens} "
        f"out={r1.output_tokens + r2.output_tokens + r3.output_tokens} "
        f"tools={len(tools_called)}"
    )
