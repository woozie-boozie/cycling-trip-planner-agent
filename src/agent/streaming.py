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

import asyncio
import json
import time
from collections.abc import AsyncIterator
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

    # Pre-build cache-marked versions of system + tools once per turn —
    # both are stable for the entire turn (and indeed the whole session,
    # unless the profile changes). Marking the LAST tool with
    # cache_control covers the entire tools array. See src/agent/caching.py.
    cached_system_blocks = cached_system(system_prompt)
    cached_tool_defs = cached_tools(tools)

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
    turn_cache_creation = 0
    turn_cache_read = 0
    tool_call_summary: list[dict[str, Any]] = []
    final_stop_reason = "end_turn"

    log.info(
        "agent.stream.start",
        session_id=state.session_id,
        messages_in=len(state.messages),
    )

    for iteration in range(1, settings.max_loop_iterations + 1):
        log.info(
            "agent.stream.iteration",
            session_id=state.session_id,
            iteration=iteration,
            messages=len(state.messages),
        )

        # We accumulate the assistant message ourselves from the streamed
        # events instead of relying on `stream.get_final_message()`. The
        # SDK's get_final_message() can return content blocks with empty
        # `.text` when called inside the async-with — a multi-turn amnesia
        # bug we hit in production (commit prior to fix shipped flat input
        # tokens across turns 6.99k → 6.96k → 7.13k because the assistant
        # turn was being persisted with empty text content).
        #
        # Per content-block index:
        #   accumulated_text[i]  → joined text from text_delta events
        #   accumulated_tool[i]  → {id, name, input} for tool_use blocks
        accumulated_text: dict[int, str] = {}
        accumulated_tool: dict[int, dict[str, Any]] = {}
        # block_order preserves insertion order so we can rebuild content[]
        # in the same sequence Claude emitted it.
        block_order: list[int] = []
        iteration_input_tokens = 0
        iteration_output_tokens = 0
        iteration_cache_creation = 0
        iteration_cache_read = 0
        iteration_stop_reason: str | None = None

        # Re-mark the message history's last block on every iteration so
        # the cache breakpoint moves forward as the conversation grows.
        # state.messages is NOT mutated — cached_messages returns a copy.
        # See orchestrator.py for the cast() rationale — same boundary, same
        # shape; the cast is purely a type-system narrowing.
        async with client.messages.stream(
            model=settings.anthropic_model,
            max_tokens=settings.max_tokens,
            system=cast(list[TextBlockParam], cached_system_blocks),
            tools=cast(list[ToolParam], cached_tool_defs),
            messages=cast(list[MessageParam], cached_messages(state.messages)),
        ) as stream:
            async for event in stream:
                event_type = getattr(event, "type", None)

                if event_type == "message_start":
                    msg = getattr(event, "message", None)
                    usage = getattr(msg, "usage", None) if msg else None
                    if usage is not None:
                        iteration_input_tokens = usage.input_tokens
                        iteration_output_tokens = usage.output_tokens
                        (
                            iteration_cache_creation,
                            iteration_cache_read,
                        ) = extract_cache_usage(usage)

                elif event_type == "content_block_start":
                    block = event.content_block
                    if event.index not in block_order:
                        block_order.append(event.index)
                    if block.type == "text":
                        accumulated_text[event.index] = ""
                    elif block.type == "tool_use":
                        accumulated_tool[event.index] = {
                            "id": block.id,
                            "name": block.name,
                            "input": {},
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
                        accumulated_text[event.index] = (
                            accumulated_text.get(event.index, "") + delta.text
                        )
                        yield {
                            "type": "text_delta",
                            "iteration": iteration,
                            "text": delta.text,
                        }
                    # input_json_delta accumulates into the SDK's
                    # current_message_snapshot; we read the assembled input
                    # on content_block_stop (next branch).

                elif event_type == "content_block_stop":
                    if event.index in accumulated_tool:
                        snapshot = stream.current_message_snapshot
                        target_id = accumulated_tool[event.index]["id"]
                        for sblock in snapshot.content:
                            if sblock.type == "tool_use" and sblock.id == target_id:
                                accumulated_tool[event.index]["input"] = dict(sblock.input)
                                yield {
                                    "type": "tool_use_complete",
                                    "iteration": iteration,
                                    "id": sblock.id,
                                    "name": sblock.name,
                                    "input": dict(sblock.input),
                                }
                                break

                elif event_type == "message_delta":
                    delta_obj = getattr(event, "delta", None)
                    if delta_obj is not None:
                        sr = getattr(delta_obj, "stop_reason", None)
                        if sr:
                            iteration_stop_reason = sr
                    usage = getattr(event, "usage", None)
                    if usage is not None:
                        # message_delta usage carries cumulative output
                        # tokens for the message — assign, don't add.
                        iteration_output_tokens = usage.output_tokens

        # Build the assistant content array from OUR accumulators. Each block
        # carries the actual text we received via text_delta events (not the
        # empty-string blocks get_final_message() would have given us).
        assistant_content: list[dict[str, Any]] = []
        # Synthesise minimal content blocks for tool_use entries we missed
        # (defensive — shouldn't happen but keeps Pydantic happy on next call)
        for idx in block_order:
            if idx in accumulated_text:
                text = accumulated_text[idx]
                # Drop empty text blocks (Claude rarely emits them, but
                # Anthropic's API rejects messages with content=[]).
                if text:
                    assistant_content.append({"type": "text", "text": text})
            elif idx in accumulated_tool:
                tb = accumulated_tool[idx]
                assistant_content.append({
                    "type": "tool_use",
                    "id": tb["id"],
                    "name": tb["name"],
                    "input": tb["input"],
                })

        if not assistant_content:
            # Anthropic's API rejects assistant turns with empty content.
            # Insert a minimal text block so the conversation remains valid
            # for the next /chat call. Surfaces the silent-failure mode in
            # the trace as well.
            log.warning(
                "agent.stream.empty_content",
                session_id=state.session_id,
                iteration=iteration,
            )
            assistant_content = [{"type": "text", "text": ""}]

        # Token accounting from streamed events (input from message_start,
        # output from cumulative message_delta). Cache stats let us see at
        # a glance how much of the input was hit-from-cache vs newly billed.
        turn_input_tokens += iteration_input_tokens
        turn_output_tokens += iteration_output_tokens
        turn_cache_creation += iteration_cache_creation
        turn_cache_read += iteration_cache_read
        state.total_input_tokens += iteration_input_tokens
        state.total_output_tokens += iteration_output_tokens

        log.info(
            "agent.stream.iteration.usage",
            session_id=state.session_id,
            iteration=iteration,
            input_tokens=iteration_input_tokens,
            output_tokens=iteration_output_tokens,
            cache_creation=iteration_cache_creation,
            cache_read=iteration_cache_read,
        )

        # Persist the assistant turn so the next iteration sees it.
        state.messages.append({"role": "assistant", "content": assistant_content})

        # Trace text + tool_use blocks. We iterate our accumulators rather
        # than the SDK's final_message — same shape, more reliable.
        for idx in block_order:
            if idx in accumulated_text and accumulated_text[idx]:
                _trace(state, iteration, "assistant_text", {"text": accumulated_text[idx]})
            elif idx in accumulated_tool:
                tb = accumulated_tool[idx]
                _trace(
                    state,
                    iteration,
                    "tool_use",
                    {"id": tb["id"], "name": tb["name"], "input": tb["input"]},
                )
                tool_call_summary.append(
                    {"name": tb["name"], "args": list(tb["input"].keys())}
                )

        stop_reason = iteration_stop_reason or "end_turn"
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
            log.info(
                "agent.stream.done",
                session_id=state.session_id,
                messages_out=len(state.messages),
                iterations=iteration,
                input_tokens=turn_input_tokens,
                output_tokens=turn_output_tokens,
                cache_creation=turn_cache_creation,
                cache_read=turn_cache_read,
            )
            yield {
                "type": "done",
                "session_id": state.session_id,
                "stop_reason": stop_reason,
                "iterations": iteration,
                "input_tokens": turn_input_tokens,
                "output_tokens": turn_output_tokens,
                "cache_read_tokens": turn_cache_read,
                "cache_creation_tokens": turn_cache_creation,
                "tool_calls": tool_call_summary,
            }
            return

        # Dispatch all tool_use blocks in PARALLEL via asyncio.as_completed.
        # SSE events fire as each tool finishes (any order, fastest first),
        # giving the UI live progress instead of a single 150s stall.
        # tool_result_blocks for the message history is reassembled in
        # block_order at the end — Anthropic's tool_use protocol expects
        # results in the same order as the original tool_use blocks.
        indexed_tool_calls = [
            (idx, accumulated_tool[idx])
            for idx in block_order
            if idx in accumulated_tool
        ]

        async def _dispatch_with_idx(
            idx: int, tb: dict[str, Any],
        ) -> tuple[int, dict[str, Any], Any, int]:
            t0 = time.perf_counter()
            r = await dispatch(tb["name"], tb["input"])
            return idx, tb, r, int((time.perf_counter() - t0) * 1000)

        tasks = [
            asyncio.create_task(_dispatch_with_idx(idx, tb))
            for idx, tb in indexed_tool_calls
        ]

        # Collect results as they complete (any order) and emit SSE events.
        # Keyed by idx so we can reassemble in block_order after.
        completed: dict[int, tuple[dict[str, Any], Any, int]] = {}
        for completed_task in asyncio.as_completed(tasks):
            idx, tb, result, latency_ms = await completed_task
            completed[idx] = (tb, result, latency_ms)
            _trace(
                state,
                iteration,
                "tool_result",
                {
                    "tool_use_id": tb["id"],
                    "name": tb["name"],
                    "is_error": result.is_error,
                    "latency_ms": latency_ms,
                },
            )
            yield {
                "type": "tool_result",
                "iteration": iteration,
                "id": tb["id"],
                "name": tb["name"],
                "is_error": result.is_error,
                "latency_ms": latency_ms,
            }

        # Build tool_result_blocks in Claude's expected order.
        tool_result_blocks: list[dict[str, Any]] = []
        for idx in block_order:
            if idx not in completed:
                continue
            tb, result, _ = completed[idx]
            tool_result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tb["id"],
                    "content": json.dumps(result.content),
                    "is_error": result.is_error,
                }
            )

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
