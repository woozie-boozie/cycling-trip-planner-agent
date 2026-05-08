"""Real-API smoke test for the agent loop.

Runs the canonical Amsterdam→Copenhagen scenario against the live Claude API
and prints the trace as it happens. Use this to confirm:

  - Your ANTHROPIC_API_KEY is valid and has access to the model
  - All four tools are being called by the agent
  - The day-by-day output looks sensible to a real cyclist

Cost: ~1-3 cents per run depending on how chatty the agent gets.

Run:
    python scripts/smoke_test.py
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from src.agent import ConversationState, run_turn

# Make sure tools auto-register before the agent runs.
import src.tools  # noqa: F401


CANONICAL_PROMPT = (
    "I want to cycle from London to Paris on the Avenue Verte. I can do around "
    "100km a day, prefer camping but want a hostel every 3rd night. Traveling in June."
)


def _short(s: str, n: int = 200) -> str:
    return s if len(s) <= n else s[:n] + "..."


async def main(prompt: str) -> None:
    print("=" * 80)
    print(f"PROMPT: {prompt}")
    print("=" * 80)
    print()

    state = ConversationState()
    print(f"session_id = {state.session_id}")
    print()

    response = await run_turn(state, prompt)

    print("\n" + "=" * 80)
    print("TRACE (chronological)")
    print("=" * 80)
    for event in state.trace:
        if event.type == "user_message":
            print(f"  [{event.iteration:02d}]  USER       → {_short(event.payload['text'])}")
        elif event.type == "assistant_text":
            print(f"  [{event.iteration:02d}]  ASSISTANT  → {_short(event.payload['text'])}")
        elif event.type == "tool_use":
            args: dict[str, Any] = event.payload["input"]
            args_pretty = ", ".join(f"{k}={v!r}" for k, v in args.items())
            print(f"  [{event.iteration:02d}]  TOOL CALL  → {event.payload['name']}({args_pretty})")
        elif event.type == "tool_result":
            err = " (ERROR)" if event.payload["is_error"] else ""
            print(
                f"  [{event.iteration:02d}]  TOOL RESULT← {event.payload['name']}"
                f" [{event.payload['latency_ms']}ms]{err}"
            )
        elif event.type == "stop":
            print(f"  [{event.iteration:02d}]  STOP       → reason={event.payload['reason']}")

    print()
    print("=" * 80)
    print("FINAL ANSWER")
    print("=" * 80)
    print(response.message)

    print()
    print("=" * 80)
    print(
        f"STATS  iterations={response.iterations}  "
        f"input_tokens={response.input_tokens}  "
        f"output_tokens={response.output_tokens}  "
        f"tool_calls={len(response.tool_calls)}"
    )
    print("=" * 80)


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else CANONICAL_PROMPT
    asyncio.run(main(prompt))
