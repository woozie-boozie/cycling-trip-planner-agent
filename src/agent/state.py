"""Conversation state, trace events, and the agent's reply object.

`ConversationState` is the single object that captures everything we need to
resume a conversation: the messages exchanged with Claude (in the exact shape
the SDK expects), the trace of tool calls / token usage for the /trace
endpoint, and accumulated cost counters.

Persisting this object as JSON later (Phase 1.12, Postgres) is a no-op because
every field is Pydantic-serializable.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

TraceEventType = Literal[
    "user_message",
    "assistant_text",
    "tool_use",
    "tool_result",
    "stop",
    "error",
]


class TraceEvent(BaseModel):
    """A single observable event in the agent loop. Surfaced via /trace."""

    timestamp: datetime
    type: TraceEventType
    payload: dict[str, Any]
    iteration: int = Field(description="Loop iteration number within the turn that produced this event")


class ConversationState(BaseModel):
    """Everything required to resume a conversation.

    `messages` is stored in Anthropic's wire format (role + content blocks),
    so we can pass it directly to `client.messages.create(messages=...)`
    without translation.
    """

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    messages: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Anthropic-shaped messages: [{role, content}, ...]",
    )

    trace: list[TraceEvent] = Field(default_factory=list)

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_turns: int = Field(default=0, description="Number of full user-message → final-answer cycles")

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


class AgentResponse(BaseModel):
    """What the agent returns to /chat after a single user turn."""

    session_id: str
    message: str = Field(description="Final assistant text, concatenated across text blocks")
    stop_reason: str
    iterations: int = Field(description="Number of LLM round-trips this turn took")
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = Field(
        default=0,
        description="Cumulative input tokens served from Anthropic's prompt cache this turn. "
        "Bills at ~10% of the regular input rate. Non-zero only when caching breakpoints hit.",
    )
    cache_creation_tokens: int = Field(
        default=0,
        description="Cumulative input tokens used to *write* new prompt-cache entries this turn. "
        "Bills at ~125% of the regular input rate — a one-off cost the next request amortises.",
    )
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Summary of tools called this turn — name + arg keys, for quick inspection",
    )
