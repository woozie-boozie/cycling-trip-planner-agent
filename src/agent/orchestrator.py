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

import json
import time
from datetime import datetime, timezone
from typing import Any

import structlog
from anthropic import AsyncAnthropic

from src.agent.config import get_settings
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.state import AgentResponse, ConversationState, TraceEvent
from src.tools import all_anthropic_definitions, dispatch

log = structlog.get_logger(__name__)


class AgentLoopExceeded(RuntimeError):
    """Raised when the agent fails to converge within max_loop_iterations."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
) -> AgentResponse:
    """Run one full user → final-answer cycle, mutating `state` in place.

    `user_message` may be either:
      - a plain string (text-only turn — the common case), or
      - a list of Anthropic content blocks (e.g. `[{type:"image",...}, {type:"text",...}]`
        for multimodal turns).

    The state object accumulates messages, traces, and token usage so that
    the next call to `run_turn` resumes the same conversation seamlessly.
    """
    settings = get_settings()
    if client is None:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    tools = all_anthropic_definitions()

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
    tool_call_summary: list[dict[str, Any]] = []

    for iteration in range(1, settings.max_loop_iterations + 1):
        log.info(
            "agent.turn.iteration",
            session_id=state.session_id,
            iteration=iteration,
            messages=len(state.messages),
        )

        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.max_tokens,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=state.messages,
        )

        # Token accounting
        turn_input_tokens += response.usage.input_tokens
        turn_output_tokens += response.usage.output_tokens
        state.total_input_tokens += response.usage.input_tokens
        state.total_output_tokens += response.usage.output_tokens

        # Append the assistant message verbatim — the next iteration needs it
        # in the messages history so Claude can see its own prior turn.
        assistant_content = [_block_to_dict(b) for b in response.content]
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

        # If Claude is done with tools, we have our final answer.
        if response.stop_reason != "tool_use":
            _trace(state, iteration, "stop", {"reason": response.stop_reason})
            final_text = "".join(b.text for b in response.content if b.type == "text")
            state.total_turns += 1
            state.touch()
            return AgentResponse(
                session_id=state.session_id,
                message=final_text,
                stop_reason=response.stop_reason or "end_turn",
                iterations=iteration,
                input_tokens=turn_input_tokens,
                output_tokens=turn_output_tokens,
                tool_calls=tool_call_summary,
            )

        # Otherwise, dispatch every tool_use block from this assistant response
        # and bundle the results into a single user message (per Anthropic's
        # tool_use protocol).
        tool_result_blocks: list[dict[str, Any]] = []
        for block in response.content:
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

        state.messages.append({"role": "user", "content": tool_result_blocks})

    # Safety net — Claude looped too many times without converging.
    state.touch()
    raise AgentLoopExceeded(
        f"Agent did not reach end_turn within {settings.max_loop_iterations} iterations"
    )
