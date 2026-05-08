"""Tool registry and dispatch.

Design goals (see docs/decisions.md ADR-002):

  - One source of truth: a tool's Pydantic input model generates the JSON schema
    that ships to Claude as `input_schema`.
  - Decorator registration: `@register_tool(...)` adds to a global registry.
  - Type-safe dispatch: `dispatch(name, arguments)` validates arguments against
    the tool's input model before invoking.
  - Errors travel as data, not exceptions, so the agent can recover. We return
    a `ToolResult` with `is_error=True` and the agent surfaces the error to the
    user (or retries with different arguments).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass(frozen=True)
class ToolResult:
    """Outcome of a tool invocation.

    `content` is the JSON-serialized output (a dict) that gets sent back to
    Claude as the `tool_result` content block.
    `is_error` follows the Anthropic API: True signals to Claude that the tool
    failed and it should adapt.
    """

    content: dict[str, Any]
    is_error: bool = False


@dataclass(frozen=True)
class ToolDef:
    """Internal record of a registered tool.

    Held in TOOL_REGISTRY. We pre-compute the Anthropic tool definition at
    registration time so request building is a dict lookup, not a reflection
    pass per request.
    """

    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[BaseModel], BaseModel]

    @property
    def anthropic_definition(self) -> dict[str, Any]:
        """Shape required by the Anthropic Messages API for the `tools` parameter.

        See https://docs.anthropic.com/en/docs/build-with-claude/tool-use
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }


TOOL_REGISTRY: dict[str, ToolDef] = {}


def register_tool(
    name: str,
    description: str,
    input_model: type[InputT],
    output_model: type[OutputT],
) -> Callable[[Callable[[InputT], OutputT]], Callable[[InputT], OutputT]]:
    """Register a tool with the global registry.

    Usage:
        @register_tool(
            name="get_route",
            description="...",
            input_model=GetRouteInput,
            output_model=GetRouteOutput,
        )
        def get_route(input: GetRouteInput) -> GetRouteOutput:
            ...
    """

    def decorator(fn: Callable[[InputT], OutputT]) -> Callable[[InputT], OutputT]:
        if name in TOOL_REGISTRY:
            raise ValueError(f"Tool {name!r} is already registered")
        TOOL_REGISTRY[name] = ToolDef(
            name=name,
            description=description,
            input_model=input_model,
            output_model=output_model,
            handler=fn,  # type: ignore[arg-type]
        )
        return fn

    return decorator


def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
    """Validate arguments and invoke the named tool.

    Returns a `ToolResult` with `is_error=True` rather than raising, so the
    agent loop can pass the error back to Claude as a `tool_result` block.
    """
    tool = TOOL_REGISTRY.get(name)
    if tool is None:
        return ToolResult(
            content={
                "error": "unknown_tool",
                "message": f"No tool named {name!r}. Known tools: {sorted(TOOL_REGISTRY)}",
            },
            is_error=True,
        )

    try:
        validated = tool.input_model.model_validate(arguments)
    except ValidationError as e:
        return ToolResult(
            content={
                "error": "invalid_arguments",
                "tool": name,
                "details": e.errors(include_url=False),
            },
            is_error=True,
        )

    try:
        result = tool.handler(validated)
    except Exception as e:  # noqa: BLE001 — we deliberately don't trust tool authors
        return ToolResult(
            content={"error": "tool_exception", "tool": name, "message": str(e)},
            is_error=True,
        )

    if not isinstance(result, tool.output_model):
        return ToolResult(
            content={
                "error": "bad_output_type",
                "tool": name,
                "expected": tool.output_model.__name__,
                "got": type(result).__name__,
            },
            is_error=True,
        )

    return ToolResult(content=result.model_dump(mode="json"), is_error=False)


def all_anthropic_definitions() -> list[dict[str, Any]]:
    """List all registered tools in the shape the Anthropic SDK wants."""
    return [tool.anthropic_definition for tool in TOOL_REGISTRY.values()]


def reset_registry_for_tests() -> None:
    """Clear the registry. Test-only helper."""
    TOOL_REGISTRY.clear()
