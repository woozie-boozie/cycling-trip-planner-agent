"""Tool package.

Importing this package registers all tools with `TOOL_REGISTRY`. Add new tools
to this import list — that's the only place needed to wire them in.
"""

from src.tools import accommodation, critique, elevation, route, weather  # noqa: F401 — register on import
from src.tools.base import (
    TOOL_REGISTRY,
    ToolDef,
    ToolResult,
    all_anthropic_definitions,
    dispatch,
    register_tool,
)

__all__ = [
    "TOOL_REGISTRY",
    "ToolDef",
    "ToolResult",
    "all_anthropic_definitions",
    "dispatch",
    "register_tool",
]
