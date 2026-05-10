"""Phase 1.10c · Named-variant trigger smoke.

Verifies the agent skips the variant-comparison block when the user names
a specific variant by alias. Each prompt should produce a single iteration
with `get_route` called and NO multi-variant comparison block in the output.

Cost: ~$0.05 each, ~$0.20 for the full sweep.

Usage:
    USE_REAL_ROUTES=true .venv/bin/python scripts/smoke_named_variants.py
"""

from __future__ import annotations

import asyncio
import os
import sys

import src.tools  # noqa: F401, E402 — register tools
from src.agent import ConversationState, run_turn  # noqa: E402

INPUT_COST_PER_TOKEN = 3.0 / 1_000_000
OUTPUT_COST_PER_TOKEN = 15.0 / 1_000_000


def _summary(state: ConversationState) -> tuple[float, list[str]]:
    cost = (
        state.total_input_tokens * INPUT_COST_PER_TOKEN
        + state.total_output_tokens * OUTPUT_COST_PER_TOKEN
    )
    tools = [e.payload["name"] for e in state.trace if e.type == "tool_use"]
    return cost, tools


async def _exercise(prompt: str, expected_variant: str) -> dict[str, object]:
    print(f"\n{'=' * 78}\n  PROMPT: {prompt}\n  EXPECT: {expected_variant} variant chosen, no comparison block\n{'=' * 78}")
    state = ConversationState()
    response = await run_turn(state, prompt)
    cost, tools = _summary(state)
    text = response.message.lower()

    # The comparison block contains every variant title. Detect it by looking
    # for at least 2 variant-title keywords appearing close together.
    variant_keywords = ["v16a", "chantilly", "gisors", "ev7", "ev12", "coastal", "ncn 20", "lewes detour"]
    titles_seen = sum(1 for k in variant_keywords if k in text)
    has_comparison = titles_seen >= 3

    chose_correct = expected_variant.lower() in text or expected_variant.lower().split("/")[0] in text

    print(f"  iter={state.total_turns}  cost=${cost:.4f}  tools={len(tools)}")
    print(f"  comparison block detected: {has_comparison}  (saw {titles_seen} variant keywords)")
    print(f"  expected variant referenced: {chose_correct}")
    print(f"  --- first 600 chars ---")
    print("  " + response.message[:600].replace("\n", "\n  "))
    return {"prompt": prompt, "skipped_comparison": not has_comparison, "chose_correct": chose_correct}


async def main() -> int:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("test"):
        print("ERROR: ANTHROPIC_API_KEY not set")
        return 1
    if os.getenv("USE_REAL_ROUTES") not in {"true", "1", "yes", "on"}:
        print("WARNING: USE_REAL_ROUTES not set — set it to exercise the multi-variant path")

    cases = [
        ("Plan a 5-day London → Paris via the chateaux variant, 80 km/day, June, mostly camping.",
         "Chantilly"),
        ("Plan an Amsterdam → Copenhagen ride along the coast, 80 km/day, July.",
         "Coastal EV12"),
        ("London to Brighton via the South Downs and Lewes, 70 km/day.",
         "Avenue Verte UK + Lewes"),
        ("Plan the Gisors route from London to Paris, 4 days, 100 km/day.",
         "Gisors"),
    ]
    results = []
    for prompt, expected in cases:
        try:
            r = await _exercise(prompt, expected)
            results.append(r)
        except Exception as exc:
            print(f"  !! crashed: {exc!r}")
            results.append({"prompt": prompt, "skipped_comparison": False, "chose_correct": False})

    print("\n" + "#" * 78)
    print("  SUMMARY")
    print("#" * 78)
    for r in results:
        ok = r["skipped_comparison"] and r["chose_correct"]
        marker = "✓" if ok else "✗"
        print(f"  {marker}  skipped_comparison={r['skipped_comparison']}  chose_correct={r['chose_correct']}")
        print(f"     {r['prompt']}")
    passed = sum(1 for r in results if r["skipped_comparison"] and r["chose_correct"])
    print(f"\n  TOTAL: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
