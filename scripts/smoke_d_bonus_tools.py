"""Phase 2D·2 live integration — does the agent actually USE the new tools?

Runs 4 real-Claude prompts targeting POI / ferry / budget. For each:
  - Full agent loop via run_turn (the production code path)
  - Reports iterations, tools called, token + cost estimate
  - Asserts the right tools fired and the answer mentions the right data

Cost per run: ~$0.05 each, ~$0.20 total. Real network + DB.

Usage:
    .venv/bin/python scripts/smoke_d_bonus_tools.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from collections import Counter

# Register tools BEFORE importing the agent so the registry is populated.
import src.tools  # noqa: F401, E402
from src.agent import ConversationState, run_turn  # noqa: E402

# Sonnet 4.6 pricing (as of 2026-05): $3/MTok input, $15/MTok output.
INPUT_COST_PER_TOKEN = 3.0 / 1_000_000
OUTPUT_COST_PER_TOKEN = 15.0 / 1_000_000


def cost_eur(state: ConversationState) -> float:
    usd = (
        state.total_input_tokens * INPUT_COST_PER_TOKEN
        + state.total_output_tokens * OUTPUT_COST_PER_TOKEN
    )
    return usd  # report in USD; close enough for a smoke run


def tools_called(state: ConversationState) -> list[str]:
    return [e.payload["name"] for e in state.trace if e.type == "tool_use"]


def banner(scenario: str, prompt: str) -> None:
    print()
    print("=" * 78)
    print(f"  {scenario}")
    print("=" * 78)
    print(f"  PROMPT: {prompt}")
    print("-" * 78)


def report(state: ConversationState, response_text: str, checks: list[tuple[str, bool]]) -> int:
    counts = Counter(tools_called(state))
    print(f"  iterations: {state.total_turns}")
    print(f"  tokens: in={state.total_input_tokens}  out={state.total_output_tokens}")
    print(f"  cost:   ~${cost_eur(state):.4f}")
    if counts:
        print(f"  tools:  {dict(counts)}")
    else:
        print("  tools:  (none called — pure text response)")

    print()
    passed = 0
    for label, ok in checks:
        marker = "✓" if ok else "✗"
        print(f"  {marker} {label}")
        if ok:
            passed += 1

    print()
    snippet = response_text.strip().replace("\n", "\n  ")
    if len(snippet) > 1200:
        snippet = snippet[:1200] + "...[truncated]"
    print("  --- agent response (first 1200 chars) ---")
    print(f"  {snippet}")
    print()
    return passed


async def s14_poi_bike_shop_london() -> tuple[int, int]:
    banner(
        "D14 · POI prompt — bike shop in London",
        "What's a good bike shop near central London? I need a derailleur tuned.",
    )
    state = ConversationState()
    t0 = time.time()
    response = await run_turn(
        state,
        "What's a good bike shop near central London? I need a derailleur tuned.",
    )
    elapsed = time.time() - t0
    print(f"  wall: {elapsed:.1f}s")

    text = response.message.lower()
    called = tools_called(state)
    checks = [
        ("get_points_of_interest called", "get_points_of_interest" in called),
        ("did NOT call get_route (irrelevant)", "get_route" not in called),
        ("response mentions a real bike shop name",
         any(name in text for name in ("brixton cycles", "cycle surgery", "holborn"))),
    ]
    return report(state, response.message, checks), len(checks)


async def s15_ferry_london_paris() -> tuple[int, int]:
    banner(
        "D15 · Ferry prompt — London → Paris with departure question",
        "Plan a 4-day London → Paris in June, 80km/day, hostel each night. Which ferry should I aim for?",
    )
    state = ConversationState()
    t0 = time.time()
    response = await run_turn(
        state,
        "Plan a 4-day London to Paris in June, 80km/day, hostel each night. "
        "Which ferry should I aim for?",
    )
    elapsed = time.time() - t0
    print(f"  wall: {elapsed:.1f}s")

    text = response.message.lower()
    called = tools_called(state)
    checks = [
        ("get_route called", "get_route" in called),
        ("get_ferry_schedule called", "get_ferry_schedule" in called),
        ("response mentions Newhaven or Dieppe",
         "newhaven" in text or "dieppe" in text),
        ("response mentions DFDS (the operator)", "dfds" in text),
        ("response mentions a specific time (HH:MM)",
         any(t in text for t in ("10:00", "22:00", "08:00", "06:00", "17:00"))),
    ]
    return report(state, response.message, checks), len(checks)


async def s16_budget_amsterdam_bremen() -> tuple[int, int]:
    banner(
        "D16 · Budget prompt — Amsterdam → Bremen with calorie question",
        "How much will a 5-day Amsterdam → Bremen camping trip cost me, and how much should I eat the night before each ride?",
    )
    state = ConversationState()
    t0 = time.time()
    response = await run_turn(
        state,
        "How much will a 5-day Amsterdam to Bremen camping trip cost me at "
        "80km/day, and how much should I eat the night before each ride?",
    )
    elapsed = time.time() - t0
    print(f"  wall: {elapsed:.1f}s")

    text = response.message.lower()
    called = tools_called(state)
    checks = [
        ("estimate_budget called", "estimate_budget" in called),
        ("response mentions a € figure", "€" in response.message or "eur" in text),
        ("response mentions calories or kcal",
         "calorie" in text or "kcal" in text or "fuel" in text),
        ("response mentions a daily kcal target near 4200",
         any(s in text for s in ("4200", "4,200", "4100", "4300"))),
    ]
    return report(state, response.message, checks), len(checks)


async def s17_combined_headline() -> tuple[int, int]:
    banner(
        "D17 · Combined — the headline Loom shot",
        "Plan a 4-day London → Paris, 100km/day, mostly camping with a hostel before the ferry. Include the ferry options and a budget.",
    )
    state = ConversationState()
    t0 = time.time()
    response = await run_turn(
        state,
        "Plan a 4-day London to Paris in June, 100km/day, mostly camping with a "
        "hostel the night before the ferry. Include the ferry options and a "
        "budget for the whole trip.",
    )
    elapsed = time.time() - t0
    print(f"  wall: {elapsed:.1f}s")

    text = response.message.lower()
    called = tools_called(state)
    counts = Counter(called)
    checks = [
        ("get_route called", "get_route" in called),
        ("get_ferry_schedule called", "get_ferry_schedule" in called),
        ("estimate_budget called", "estimate_budget" in called),
        ("get_elevation_profile called >=2x", counts["get_elevation_profile"] >= 2),
        ("get_weather called >=2x", counts["get_weather"] >= 2),
        ("find_accommodation called >=2x", counts["find_accommodation"] >= 2),
        ("critique_trip_plan called", "critique_trip_plan" in called),
        ("output is a day-by-day plan",
         "day 1" in text and "day 2" in text and "day 3" in text and "day 4" in text),
        ("output mentions ferry crossing", "ferry" in text or "dieppe" in text),
        ("output mentions a € figure", "€" in response.message or "eur" in text),
    ]
    return report(state, response.message, checks), len(checks)


async def main() -> int:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "test-key-not-real":
        print("ERROR: ANTHROPIC_API_KEY not set in environment.")
        return 1

    scenarios = [
        ("D14 POI", s14_poi_bike_shop_london),
        ("D15 Ferry", s15_ferry_london_paris),
        ("D16 Budget", s16_budget_amsterdam_bremen),
        ("D17 Combined", s17_combined_headline),
    ]
    summary: list[tuple[str, int, int]] = []
    for label, fn in scenarios:
        try:
            passed, total = await fn()
            summary.append((label, passed, total))
        except Exception as exc:  # pragma: no cover — smoke script
            print(f"\n  !! {label} crashed: {exc!r}")
            summary.append((label, 0, 0))

    print()
    print("#" * 78)
    print("  SUMMARY")
    print("#" * 78)
    total_passed = 0
    total_checks = 0
    for label, passed, total in summary:
        marker = "✓" if passed == total else "•"
        print(f"  {marker}  {label:<20s}  {passed}/{total} checks")
        total_passed += passed
        total_checks += total
    print(f"\n  TOTAL: {total_passed}/{total_checks} checks passed")
    print("#" * 78)
    return 0 if total_passed == total_checks else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
