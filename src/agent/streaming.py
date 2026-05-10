"""Streaming agent loop — yields events as Claude emits them.

Mirrors `run_turn()` from `orchestrator.py` but uses Anthropic's
`messages.stream()` API and yields a typed sequence of events the
frontend consumes via Server-Sent Events.

Why a parallel implementation, not a streaming wrapper of `run_turn`:
the tool-use loop has TWO interleaved concerns — emitting the agent's
text/tool events as they happen (streaming) and then synchronously
dispatching tools and feeding results back. Bolting a callback onto
`run_turn` would muddy the synchronous code path; a parallel
generator-based implementation keeps each path clean.

Event protocol (dict shape, JSON-serialisable):

  {"type": "text_delta", "iteration": N, "text": "..."}
    Token-by-token text from Claude. Concatenate to update the live
    assistant message bubble.

  {"type": "tool_use_start", "iteration": N, "id": "...", "name": "..."}
    A tool_use content block has begun. Args haven't streamed yet.

  {"type": "tool_use_complete", "iteration": N, "id": "...", "name": "...",
   "input": {...}}
    The tool_use block's args are fully assembled. Backend has not
    dispatched the tool yet.

  {"type": "tool_result", "iteration": N, "id": "...", "name": "...",
   "is_error": false, "latency_ms": N}
    Backend dispatched the tool and got a result.

  {"type": "iteration_end", "iteration": N, "stop_reason": "..."}
    The model's response for this iteration is fully assembled. If
    stop_reason == "tool_use", the agent loop continues; otherwise
    a "done" event follows next.

  {"type": "done", "session_id": "...", "iterations": N,
   "input_tokens": N, "output_tokens": N, "tool_calls": [...]}
    Final event — the turn is complete.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import structlog
from anthropic import AsyncAnthropic

from src.agent.config import get_settings
from src.agent.prompts import SYSTEM_PROMPT, user_profile_context
from src.agent.state import ConversationState, TraceEvent
from src.sessions import UserProfile
from src.tools import all_anthropic_definitions, dispatch

log = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _block_to_dict(block: Any) -> dict[str, Any]:
    return block.model_dump(mode="json", exclude_none=True)


def _trace(state: ConversationState, iteration: int, type_: str, payload: dict[str, Any]) -> None:
    state.trace.append(
        TraceEvent(timestamp=_now(), iteration=iteration, type=type_, payload=payload)  # type: ignore[arg-type]
    )


async def run_turn_stream(
    state: ConversationState,
    user_message: str | list[dict[str, Any]],
    *,
    client: AsyncAnthropic | None = None,
    profile: UserProfile | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Streaming counterpart to ``run_turn``.

    Yields events as the agent reasons. Mutates ``state`` exactly the same
    way ``run_turn`` does — same messages appended, same trace events —
    so ``GET /trace/{session_id}`` keeps working unchanged.
    """
    settings = get_settings()
    if client is None:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    tools = all_anthropic_definitions()

    system_prompt = SYSTEM_PROMPT
    if profile is not None:
        system_prompt = SYSTEM_PROMPT + "\n\n" + user_profile_context(profile)

    # Append the user's message to the conversation (same as run_turn).
    state.messages.append({"role": "user", "content": user_message})

    if isinstance(user_message, str):
        trace_payload: dict[str, Any] = {"text": user_message}
    else:
        text_parts = [b.get("text", "") for b in user_message if b.get("type") == "text"]
        image_count = sum(1 for b in user_message if b.get("type") == "image")
        trace_payload = {"text": "\n".join(text_parts), "images": image_count}
    _trace(state, iteration=0, type_="user_message", payload=trace_payload)

    turn_input_tokens = 0
    turn_output_tokens = 0
    tool_call_summary: list[dict[str, Any]] = []
    final_stop_reason = "end_turn"

    for iteration in range(1, settings.max_loop_iterations + 1):
        log.info(
            "agent.stream.iteration",
            session_id=state.session_id,
            iteration=iteration,
            messages=len(state.messages),
        )

        # `messages.stream()` is an async context manager that yields
        # structured events. We translate them to our flat dict protocol.
        # Track which content-block index is the currently-open tool_use
        # so we know which one to emit complete-events for.
        open_tool_blocks: dict[int, dict[str, Any]] = {}

        async with client.messages.stream(
            model=settings.anthropic_model,
            max_tokens=settings.max_tokens,
            system=system_prompt,
            tools=tools,
            messages=state.messages,
        ) as stream:
            async for event in stream:
                event_type = getattr(event, "type", None)

                if event_type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        open_tool_blocks[event.index] = {
                            "id": block.id,
                            "name": block.name,
                        }
                        yield {
                            "type": "tool_use_start",
                            "iteration": iteration,
                            "id": block.id,
                            "name": block.name,
                        }

                elif event_type == "content_block_delta":
                    delta = event.delta
                    delta_type = getattr(delta, "type", None)
                    if delta_type == "text_delta":
                        yield {
                            "type": "text_delta",
                            "iteration": iteration,
                            "text": delta.text,
                        }
                    # input_json_delta events stream tool args incrementally —
                    # we emit the assembled input on content_block_stop instead
                    # of streaming partial JSON, which the frontend can't
                    # usefully render mid-build.

                elif event_type == "content_block_stop":
                    if event.index in open_tool_blocks:
                        # Pull the assembled tool_use block from the snapshot
                        # so we have the full input dict.
                        snapshot = stream.current_message_snapshot
                        for sblock in snapshot.content:
                            if (
                                sblock.type == "tool_use"
                                and sblock.id == open_tool_blocks[event.index]["id"]
                            ):
                                yield {
                                    "type": "tool_use_complete",
                                    "iteration": iteration,
                                    "id": sblock.id,
                                    "name": sblock.name,
                                    "input": dict(sblock.input),
                                }
                                break
                        del open_tool_blocks[event.index]

            final_message = await stream.get_final_message()

        # Token accounting (same as run_turn).
        turn_input_tokens += final_message.usage.input_tokens
        turn_output_tokens += final_message.usage.output_tokens
        state.total_input_tokens += final_message.usage.input_tokens
        state.total_output_tokens += final_message.usage.output_tokens

        # Append the assistant message verbatim so the next iteration sees it.
        assistant_content = [_block_to_dict(b) for b in final_message.content]
        state.messages.append({"role": "assistant", "content": assistant_content})

        # Trace text + tool_use blocks (same as run_turn).
        for block in final_message.content:
            if block.type == "text":
                _trace(state, iteration, "assistant_text", {"text": block.text})
            elif block.type == "tool_use":
                _trace(
                    state,
                    iteration,
                    "tool_use",
                    {"id": block.id, "name": block.name, "input": dict(block.input)},
                )
                tool_call_summary.append(
                    {"name": block.name, "args": list(dict(block.input).keys())}
                )

        stop_reason = final_message.stop_reason or "end_turn"
        final_stop_reason = stop_reason
        yield {
            "type": "iteration_end",
            "iteration": iteration,
            "stop_reason": stop_reason,
        }

        if stop_reason != "tool_use":
            _trace(state, iteration, "stop", {"reason": stop_reason})
            state.total_turns += 1
            state.touch()
            yield {
                "type": "done",
                "session_id": state.session_id,
                "stop_reason": stop_reason,
                "iterations": iteration,
                "input_tokens": turn_input_tokens,
                "output_tokens": turn_output_tokens,
                "tool_calls": tool_call_summary,
            }
            return

        # Otherwise, dispatch every tool_use block and yield results.
        tool_result_blocks: list[dict[str, Any]] = []
        for block in final_message.content:
            if block.type != "tool_use":
                continue
            t0 = time.perf_counter()
            result = await dispatch(block.name, dict(block.input))
            latency_ms = int((time.perf_counter() - t0) * 1000)

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
            yield {
                "type": "tool_result",
                "iteration": iteration,
                "id": block.id,
                "name": block.name,
                "is_error": result.is_error,
                "latency_ms": latency_ms,
            }

        state.messages.append({"role": "user", "content": tool_result_blocks})

    # Loop budget exhausted — yield a terminal error event.
    state.touch()
    yield {
        "type": "done",
        "session_id": state.session_id,
        "stop_reason": "loop_exceeded",
        "iterations": settings.max_loop_iterations,
        "input_tokens": turn_input_tokens,
        "output_tokens": turn_output_tokens,
        "tool_calls": tool_call_summary,
        "error": (
            f"Agent did not converge within {settings.max_loop_iterations} iterations "
            f"(last stop_reason: {final_stop_reason})"
        ),
    }
