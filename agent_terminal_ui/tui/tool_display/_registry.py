#!/usr/bin/python
# coding: utf-8
"""Registry for tool display formatters.

This module provides a centralized registry for managing how different tools
are rendered in the terminal UI. It allows custom formatters to be
registered for specific MCP tools while providing a sane default for
unknown tools.
"""

from agent_terminal_ui.tui.tool_display._formatters import (
    DefaultToolDisplayFormatter,
    EditToolFormatter,
    TodoToolFormatter,
    ToolDisplayFormatter,
)

_registry: dict[str, ToolDisplayFormatter] = {}
_default: ToolDisplayFormatter = DefaultToolDisplayFormatter()


def register_formatter(tool_name: str, formatter: ToolDisplayFormatter) -> None:
    """Register a custom display formatter for a specific tool name.

    Args:
        tool_name: The identifier of the tool (e.g., 'git_commit').
        formatter: An object implementing the ToolDisplayFormatter protocol.

    """
    _registry[tool_name] = formatter


def get_formatter(tool_name: str) -> ToolDisplayFormatter:
    """Retrieve the appropriate formatter for a given tool.

    Falls back to the DefaultToolDisplayFormatter if no specific
    formatter is registered for the tool.

    Args:
        tool_name: The identifier of the tool to format.

    Returns:
        The registered formatter or the default implementation.

    """
    return _registry.get(tool_name, _default)


# Auto-register built-in formatters for core agent-utilities tools
register_formatter("edit", EditToolFormatter())
register_formatter("todo_write", TodoToolFormatter())
