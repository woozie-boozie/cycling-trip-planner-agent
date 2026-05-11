"""Prompt-caching helpers for Anthropic API calls.

The agent's stable prefix on every turn — system prompt, tool definitions,
and the message history up to the current request — is mostly identical
between iterations of a single turn AND between consecutive turns of a
session. Marking these with ``cache_control={"type": "ephemeral"}``
tells Anthropic to cache the KV-state of that prefix; subsequent
requests within 5 minutes get billed at ~10 % of the regular input-token
rate for the cached portion AND count proportionally less toward the
per-minute rate limit.

We use three cache breakpoints (out of the API's 4-max):
  1. System prompt — stable across an entire session.
  2. Tools — stable across an entire session.
  3. Last message in history — rolling breakpoint that caches the growing
     conversation up to the most-recent turn. Each request re-uses the
     previous request's cached prefix.

The helpers return *shallow copies* with cache_control set just-in-time;
the underlying ``state.messages`` is never mutated. cache_control on
content blocks is request-scoped — never persist it.
"""

from __future__ import annotations

from typing import Any

_EPHEMERAL: dict[str, str] = {"type": "ephemeral"}


def cached_system(system_prompt: str) -> list[dict[str, Any]]:
    """Wrap the system prompt string in a single text block with a
    cache breakpoint. Anthropic caches everything in the system field
    up to and including this block."""
    return [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": _EPHEMERAL,
        }
    ]


def cached_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark the LAST tool definition with cache_control so the entire
    tools array is cached. Returns a shallow copy; the input list isn't
    mutated."""
    if not tools:
        return tools
    out = list(tools)
    last = dict(out[-1])
    last["cache_control"] = _EPHEMERAL
    out[-1] = last
    return out


def cached_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply cache_control to the FINAL content block of the LAST message
    so Anthropic caches the full conversation history up to that point.

    Two cases for the last message's ``content``:
      * ``str`` — wrap as a single text block with cache_control.
      * ``list[dict]`` — set cache_control on the last block (typically
        a ``tool_result`` mid-turn or ``text`` end-of-turn).

    Returns a new list with shallow-copied last message + content; the
    original ``messages`` list and its dicts are NOT mutated.
    """
    if not messages:
        return messages
    out = list(messages)
    last = dict(out[-1])
    content = last.get("content")
    if isinstance(content, str):
        last["content"] = [
            {"type": "text", "text": content, "cache_control": _EPHEMERAL}
        ]
    elif isinstance(content, list) and content:
        new_content = list(content)
        new_last_block = dict(new_content[-1])
        new_last_block["cache_control"] = _EPHEMERAL
        new_content[-1] = new_last_block
        last["content"] = new_content
    out[-1] = last
    return out


def extract_cache_usage(usage: Any) -> tuple[int, int]:
    """Pull ``cache_creation_input_tokens`` + ``cache_read_input_tokens``
    off an Anthropic ``Usage`` object (or ``None`` shaped like one).
    Returns ``(creation, read)`` — both default to 0 when fields are
    missing (older SDK versions / non-cached responses).
    """
    if usage is None:
        return 0, 0
    creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    return int(creation), int(read)
