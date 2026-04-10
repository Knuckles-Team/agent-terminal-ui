"""Registry for tool display formatters."""

from agent_tui.tui.tool_display._formatters import (
    DefaultToolDisplayFormatter,
    EditToolFormatter,
    TodoToolFormatter,
    ToolDisplayFormatter,
)

_registry: dict[str, ToolDisplayFormatter] = {}
_default = DefaultToolDisplayFormatter()


def register_formatter(tool_name: str, formatter: ToolDisplayFormatter) -> None:
    """Register a custom formatter for a tool."""
    _registry[tool_name] = formatter


def get_formatter(tool_name: str) -> ToolDisplayFormatter:
    """Get the formatter for a tool (falls back to default)."""
    return _registry.get(tool_name, _default)


# Auto-register built-in formatters
register_formatter("edit", EditToolFormatter())
register_formatter("todo_write", TodoToolFormatter())
