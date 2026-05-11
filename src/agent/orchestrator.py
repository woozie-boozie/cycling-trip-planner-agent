"""Agent orchestrator — the tool-use loop.

This is the heart of the system. Read it top-to-bottom and you'll understand
exactly how the agent reasons:

  1. The user message gets appended to the conversation.
  2. We call Claude with the full message history, the system prompt, and the
     auto-generated tool definitions.
  3. If Claude returns tool_use blocks, we dispatch each through our tool
     registry, append the tool_result blocks as a user message, and loop.
  4. When Claude stops asking for tools (stop_reason != "tool_use"), the final
     text is our answer.

We deliberately keep this a plain async function instead of wrapping it in
a class. There's no hidden state, nothing the reader has to chase across
files. (See docs/decisions.md ADR-001.)
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from typing import Any, cast

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, TextBlockParam, ToolParam

from src.agent.caching import (
    cached_messages,
    cached_system,
    cached_tools,
    extract_cache_usage,
)
from src.agent.config import get_settings
from src.agent.prompts import SYSTEM_PROMPT, user_profile_context
from src.agent.state import AgentResponse, ConversationState, TraceEvent
from src.sessions import UserProfile
from src.tools import all_anthropic_definitions, dispatch

log = structlog.get_logger(__name__)


class AgentLoopExceeded(RuntimeError):
    """Raised when the agent fails to converge within max_loop_iterations."""


# Plan-shaped output detector — matches the agent's prescribed format from
# prompts.py L145-149:  "## Day 3 — Bremen → Hamburg".
#
# Looks for a markdown header (##, ###) followed by "Day" + a digit. The
# guardrail uses this signal to decide whether the agent's final text "looks
# like a plan presentation," and therefore should have been preceded by a
# critique_trip_plan call. False negatives (the agent uses a different
# format) → no guardrail, agent ships the plan unchecked. False positives
# (a "Day N" appears in an answer that isn't a plan) → one extra loop
# iteration with a nudge that Claude will ignore in 99% of cases. Cheap
# either way.
_PLAN_HEADER_RE = re.compile(r"(?im)^\s{0,3}#{1,3}\s*Day\s+\d+\b")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _looks_like_plan_presentation(text: str) -> bool:
    """Heuristic: does ``text`` look like the agent presenting a multi-day plan?

    Two-of-two signal — a single "Day 1" match isn't enough (could be a
    clarifying question, a single-day suggestion, or a planning preview).
    Requires at least two distinct day-headers, which is the floor for
    "actual multi-day plan being shipped to the user." Tunable.
    """
    matches = _PLAN_HEADER_RE.findall(text)
    return len(matches) >= 2


def _critique_called_in_turn(state: ConversationState, since_trace_idx: int) -> bool:
    """True iff ``critique_trip_plan`` was invoked at least once in the
    trace events added during this turn.

    ``since_trace_idx`` is captured at the very top of ``run_turn`` so we
    only see THIS turn's events, not stale events from prior turns.
    """
    for event in state.trace[since_trace_idx:]:
        if event.type == "tool_use" and event.payload.get("name") == "critique_trip_plan":
            return True
    return False


def _block_to_dict(block: Any) -> dict[str, Any]:
    """Convert an Anthropic SDK content block into a plain dict suitable for
    re-passing on the next API call AND for JSON-persisting in session state.

    The SDK's content blocks are Pydantic models, so model_dump handles this
    cleanly. We exclude None-valued fields to keep the wire payload tight.
    """
    return block.model_dump(mode="json", exclude_none=True)


def _trace(state: ConversationState, iteration: int, type_: str, payload: dict[str, Any]) -> None:
    state.trace.append(
        TraceEvent(timestamp=_now(), iteration=iteration, type=type_, payload=payload)  # type: ignore[arg-type]
    )


async def run_turn(
    state: ConversationState,
    user_message: str | list[dict[str, Any]],
    *,
    client: AsyncAnthropic | None = None,
    profile: UserProfile | None = None,
) -> AgentResponse:
    """Run one full user → final-answer cycle, mutating `state` in place.

    `user_message` may be either:
      - a plain string (text-only turn — the common case), or
      - a list of Anthropic content blocks (e.g. `[{type:"image",...}, {type:"text",...}]`
        for multimodal turns).

    `profile` is the cyclist's onboarding profile (Phase 2D). When supplied,
    a personalisation fragment is appended to the system prompt for THIS turn
    only — it's not stored in `state.messages` so prompt edits take effect
    immediately on every existing session.

    The state object accumulates messages, traces, and token usage so that
    the next call to `run_turn` resumes the same conversation seamlessly.
    """
    settings = get_settings()
    if client is None:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    tools = all_anthropic_definitions()

    # Build the per-turn system prompt — base + (optional) profile context.
    # Profile lives outside `state.messages` so we never serialise it into
    # the turn history; the agent always sees the freshest profile data.
    system_prompt = SYSTEM_PROMPT
    if profile is not None:
        system_prompt = SYSTEM_PROMPT + "\n\n" + user_profile_context(profile)

    # Pre-build cache-marked versions of the prefix (system + tools).
    # Both are stable for the entire turn so we only build them once.
    cached_system_blocks = cached_system(system_prompt)
    cached_tool_defs = cached_tools(tools)

    # Snapshot trace length BEFORE adding any events from this turn so the
    # guardrail can scope its "did critique_trip_plan run THIS turn?" check.
    # Without this, a critique call from any prior turn would falsely
    # satisfy the guardrail for this turn's plan presentation.
    trace_start_idx = len(state.trace)

    # Append the user's message to the conversation.
    state.messages.append({"role": "user", "content": user_message})

    # Trace event — for multimodal turns, summarise: trace stays compact even
    # when the message includes a multi-MB base64 image payload.
    if isinstance(user_message, str):
        trace_payload: dict[str, Any] = {"text": user_message}
    else:
        text_parts = [b.get("text", "") for b in user_message if b.get("type") == "text"]
        image_count = sum(1 for b in user_message if b.get("type") == "image")
        trace_payload = {
            "text": "\n".join(text_parts),
            "images": image_count,
        }
    _trace(state, iteration=0, type_="user_message", payload=trace_payload)

    turn_input_tokens = 0
    turn_output_tokens = 0
    turn_cache_creation = 0
    turn_cache_read = 0
    tool_call_summary: list[dict[str, Any]] = []
    # Has the prompt-following guardrail already nudged the agent this turn?
    # We allow exactly one nudge per turn so a Claude that ignores the
    # nudge can't trap us in an infinite loop. The agent loop's
    # max_loop_iterations is the outer safety net.
    guardrail_fired = False

    for iteration in range(1, settings.max_loop_iterations + 1):
        log.info(
            "agent.turn.iteration",
            session_id=state.session_id,
            iteration=iteration,
            messages=len(state.messages),
        )

        # Re-mark the message history's last block on every iteration so
        # the cache breakpoint moves forward as the conversation grows.
        # state.messages is NOT mutated — cached_messages returns a copy.
        #
        # cast() bridges our internal list[dict[str, Any]] storage (chosen so
        # ConversationState round-trips losslessly through model_dump_json)
        # to the Anthropic SDK's typed TextBlockParam / ToolParam /
        # MessageParam TypedDicts. Shape is identical at runtime — the cast
        # is purely a type-system narrowing at the boundary.
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.max_tokens,
            system=cast(list[TextBlockParam], cached_system_blocks),
            tools=cast(list[ToolParam], cached_tool_defs),
            messages=cast(list[MessageParam], cached_messages(state.messages)),
        )

        # Token accounting
        turn_input_tokens += response.usage.input_tokens
        turn_output_tokens += response.usage.output_tokens
        cache_creation, cache_read = extract_cache_usage(response.usage)
        turn_cache_creation += cache_creation
        turn_cache_read += cache_read
        state.total_input_tokens += response.usage.input_tokens
        state.total_output_tokens += response.usage.output_tokens

        log.info(
            "agent.turn.iteration.usage",
            session_id=state.session_id,
            iteration=iteration,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_creation=cache_creation,
            cache_read=cache_read,
        )

        # Append the assistant message verbatim — the next iteration needs it
        # in the messages history so Claude can see its own prior turn.
        #
        # Defensive: Anthropic's API rejects messages with content=[] on the
        # NEXT call. If response.content is empty (SDK edge case, contract
        # violation, or a transport that dropped blocks), substitute a
        # minimal text block so the conversation remains valid. Mirrors the
        # same guard in streaming.py:276-286. Logs at WARN so silent
        # corruption surfaces in observability.
        assistant_content = [_block_to_dict(b) for b in response.content]
        if not assistant_content:
            log.warning(
                "agent.turn.empty_content",
                session_id=state.session_id,
                iteration=iteration,
                stop_reason=response.stop_reason,
            )
            assistant_content = [{"type": "text", "text": ""}]
        state.messages.append({"role": "assistant", "content": assistant_content})

        # Trace text + tool_use blocks for observability
        for block in response.content:
            if block.type == "text":
                _trace(state, iteration, "assistant_text", {"text": block.text})
            elif block.type == "tool_use":
                _trace(
                    state,
                    iteration,
                    "tool_use",
                    {"id": block.id, "name": block.name, "input": block.input},
                )
                tool_call_summary.append(
                    {"name": block.name, "args": list(dict(block.input).keys())}
                )

        # If Claude is done with tools, we have our final answer — UNLESS
        # the prompt-following guardrail catches a contract violation.
        if response.stop_reason != "tool_use":
            final_text = "".join(b.text for b in response.content if b.type == "text")

            # GUARDRAIL — the system prompt MANDATES critique_trip_plan
            # before presenting any multi-day plan (prompts.py Step 4). If
            # Claude shipped a plan-shaped response without calling it,
            # nudge it to comply rather than letting a contract violation
            # slip through to the user. The guardrail is the difference
            # between "the system prompt suggests" and "the orchestrator
            # enforces" — see ADR-008 / README architecture section.
            #
            # Fires AT MOST ONCE per turn: a second violation after the
            # nudge is rare enough that we just ship and log, letting the
            # outer eval suite catch it offline.
            if (
                not guardrail_fired
                and _looks_like_plan_presentation(final_text)
                and not _critique_called_in_turn(state, trace_start_idx)
            ):
                guardrail_fired = True
                _trace(
                    state,
                    iteration,
                    "tool_use",  # piggyback on existing type for trace replay
                    {
                        "id": f"guardrail_iter_{iteration}",
                        "name": "_guardrail_critique_missing",
                        "input": {"reason": "plan_without_critique"},
                    },
                )
                log.warning(
                    "agent.turn.guardrail_critique_missing",
                    session_id=state.session_id,
                    iteration=iteration,
                    final_text_chars=len(final_text),
                )
                # The assistant draft is already in state.messages (appended
                # at the top of this iteration), so Claude sees its own
                # draft on the next iteration. We just append the nudge as
                # a synthetic user message.
                state.messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Hold on — before you present that plan to me, you "
                            "MUST call `critique_trip_plan` on the day list you "
                            "just drafted (Step 4 of your planning flow). The "
                            "critique is a deterministic Python check, not an "
                            "LLM call — fast and free. Run it, then either "
                            "ship the plan as-is (ship_it), surface its "
                            "warnings in a Heads up section (minor_revisions), "
                            "or revise the plan before re-presenting "
                            "(major_revisions). Don't skip this step."
                        ),
                    }
                )
                # Loop again. Don't increment total_turns yet — the user's
                # message was processed but we haven't yet shipped a final
                # answer for this turn.
                continue

            _trace(state, iteration, "stop", {"reason": response.stop_reason})
            state.total_turns += 1
            state.touch()
            log.info(
                "agent.turn.done",
                session_id=state.session_id,
                iterations=iteration,
                input_tokens=turn_input_tokens,
                output_tokens=turn_output_tokens,
                cache_creation=turn_cache_creation,
                cache_read=turn_cache_read,
                guardrail_fired=guardrail_fired,
            )
            return AgentResponse(
                session_id=state.session_id,
                message=final_text,
                stop_reason=response.stop_reason or "end_turn",
                iterations=iteration,
                input_tokens=turn_input_tokens,
                output_tokens=turn_output_tokens,
                cache_read_tokens=turn_cache_read,
                cache_creation_tokens=turn_cache_creation,
                tool_calls=tool_call_summary,
            )

        # Dispatch every tool_use block from this assistant response IN
        # PARALLEL (asyncio.gather), then bundle the results into a single
        # user message in Claude's original order per the Anthropic tool_use
        # protocol. Each tool's inputs are independent — get_elevation_profile
        # for segment A doesn't read get_weather for segment B — so the
        # serial loop here was leaving 30–80% of latency on the table on
        # fan-out heavy turns. Real LDN→Edinburgh request before this change:
        # 5 BRouter timeouts × 30s = 150s serial. After: max(timeouts) ≈ 10s.
        # Tracing still records each tool's individual latency_ms.
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        tool_result_blocks: list[dict[str, Any]] = []
        if tool_use_blocks:
            async def _dispatch_one(b: Any) -> tuple[Any, int]:
                t0 = time.perf_counter()
                r = await dispatch(b.name, dict(b.input))
                return r, int((time.perf_counter() - t0) * 1000)

            results = await asyncio.gather(
                *(_dispatch_one(b) for b in tool_use_blocks),
            )

            for block, (result, latency_ms) in zip(tool_use_blocks, results):
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result.content),
                        "is_error": result.is_error,
                    }
                )
                _trace(
                    state,
                    iteration,
                    "tool_result",
                    {
                        "tool_use_id": block.id,
                        "name": block.name,
                        "is_error": result.is_error,
                        "latency_ms": latency_ms,
                    },
                )

        # Defensive: per Anthropic's tool-use protocol, stop_reason=="tool_use"
        # implies content carried at least one tool_use block, so this branch
        # is unreachable in normal flow. But a contract violation (SDK bug,
        # truncation, fuzzed response) would silently append an empty user
        # message → next API call rejects with 400. Guard against it.
        if not tool_result_blocks:
            log.warning(
                "agent.turn.empty_tool_results",
                session_id=state.session_id,
                iteration=iteration,
                tool_use_blocks=len(tool_use_blocks),
            )
            # Nothing to send back as tool_result. Break out — the safety net
            # at the bottom of the loop will raise AgentLoopExceeded with the
            # iteration count so the failure is visible to the caller.
            break
        state.messages.append({"role": "user", "content": tool_result_blocks})

    # Safety net — Claude looped too many times without converging.
    state.touch()
    raise AgentLoopExceeded(
        f"Agent did not reach end_turn within {settings.max_loop_iterations} iterations"
    )
