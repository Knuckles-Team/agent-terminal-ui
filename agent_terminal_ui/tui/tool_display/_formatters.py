#!/usr/bin/python
"""Tool display formatters for the terminal UI.

This module defines the protocol and implementations for formatting tool
calls and their outputs for visual display in the Textual-based event log.
"""

import json
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AgentToolCallEvent(Protocol):
    """Protocol for a tool call event payload."""

    name: str
    arguments: str
    call_id: str


@runtime_checkable
class AgentToolOutputEvent(Protocol):
    """Protocol for a tool execution result payload."""

    name: str
    output: dict[str, Any]
    call_id: str


class ToolDisplayFormatter(Protocol):
    """Protocol for formatting tool calls and outputs for display."""

    def format_call_header(self, event: AgentToolCallEvent) -> str:
        """Format the tool call header line.

        Args:
            event: The tool call event.

        Returns:
            A string representing the visual header (e.g., "Update(file.py)").

        """
        ...

    def format_output_summary(self, event: AgentToolOutputEvent) -> str | None:
        """Format a one-line summary of the tool output.

        Args:
            event: The tool output event.

        Returns:
            A one-line summary string, or None if no summary is needed.

        """
        ...

    def format_output_details(self, event: AgentToolOutputEvent) -> str | None:
        """Format detailed output (e.g., diff view, file contents).

        Args:
            event: The tool output event.

        Returns:
            The detailed output string, or None if no details are needed.

        """
        ...


class DefaultToolDisplayFormatter:
    """Default formatter that works for any tool.

    Provides a generic implementation that parses JSON arguments and
    summarizes output based on line counts.
    """

    def format_call_header(self, event: AgentToolCallEvent) -> str:
        """Format the header using tool name and primary parameters."""
        args = self._parse_arguments(event.arguments)
        primary = self._find_primary_param(args)
        if primary:
            return f"{event.name}({primary})"
        params_str = ", ".join(f"{k}={self._truncate(v)}" for k, v in args.items())
        return f"{event.name}({params_str})"

    def format_output_summary(self, event: AgentToolOutputEvent) -> str | None:
        """Summarize output based on the number of result lines."""
        result = self._get_result(event.output)
        if not result:
            return "Completed"
        line_count = result.count("\n") + 1
        return f"{line_count} lines" if line_count > 1 else "1 line"

    def format_output_details(self, event: AgentToolOutputEvent) -> str | None:
        """Show a truncated preview of the command output."""
        result = self._get_result(event.output)
        if not result:
            return None
        max_lines = 3
        lines = result.split("\n")
        if len(lines) > max_lines:
            return (
                "\n".join(lines[:max_lines])
                + f"\n... ({len(lines) - max_lines} more lines)"
            )
        return result

    def _parse_arguments(self, arguments: str) -> dict[str, Any]:
        """Attempt to parse the string arguments as JSON."""
        if not arguments:
            return {}
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return {}

    def _find_primary_param(self, args: dict[str, Any]) -> str | None:
        """Identify a primary parameter (e.g., 'path') for the header."""
        for key in ("file_path", "path", "command", "pattern"):
            if key in args:
                return str(args[key])
        return None

    def _truncate(self, value: Any, max_len: int = 50) -> str:
        """Truncate a string representation of a value."""
        s = str(value)
        return s if len(s) <= max_len else s[:max_len] + "..."

    def _get_result(self, output: dict[str, Any]) -> str:
        """Safely extract the 'result' field from a tool output dictionary."""
        result = output.get("result", "")
        return result if isinstance(result, str) else ""


class EditToolFormatter:
    """Custom formatter for file editing tool calls.

    Displays unified diff counts (added/removed) as a summary.
    """

    display_name: str = "Update"

    def format_call_header(self, event: AgentToolCallEvent) -> str:
        """Format the header showing the file path being edited."""
        args = self._parse_arguments(event.arguments)
        file_path = args.get("file_path", "unknown")
        return f"{self.display_name}({file_path})"

    def format_output_summary(self, event: AgentToolOutputEvent) -> str | None:
        """Summarize the number of lines added or removed in the diff."""
        result = self._get_result(event.output)
        if not result:
            return "Applied changes"
        added, removed = self._count_changes(result)
        if removed > 0 and added == 0:
            return f"Removed {removed} lines"
        if added > 0 and removed == 0:
            return f"Added {added} lines"
        if added > 0 and removed > 0:
            return f"Changed {removed} -> {added} lines"
        return "Applied changes"

    def format_output_details(self, event: AgentToolOutputEvent) -> str | None:
        """Return the full diff as the detailed view."""
        return self._get_result(event.output) or None

    def _parse_arguments(self, arguments: str) -> dict[str, Any]:
        """Attempt to parse the string arguments as JSON."""
        if not arguments:
            return {}
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return {}

    def _count_changes(self, result: str) -> tuple[int, int]:
        """Count line additions and deletions from a unified diff string."""
        added = result.count("\n+")
        removed = result.count("\n-")
        return added, removed

    def _get_result(self, output: dict[str, Any]) -> str:
        """Safely extract the 'result' field from a tool output dictionary."""
        result = output.get("result", "")
        return result if isinstance(result, str) else ""


class TodoToolFormatter:
    """Custom formatter for todo_write and task tracking tool calls.

    Renders a formatted task list with status indicators ([x], [~], [ ]).
    """

    display_name: str = "Todos"

    def __init__(self) -> None:
        """Initialize the todo formatter."""
        self._last_call_event: AgentToolCallEvent | None = None

    def format_call_header(self, event: AgentToolCallEvent) -> str:
        """Store the call event for later reference and return the display name."""
        self._last_call_event = event
        return self.display_name

    def format_output_summary(self, event: AgentToolOutputEvent) -> str | None:
        """Summarize the task progress (e.g., '2/5 completed')."""
        todos = self._parse_todos()
        if not todos:
            return None
        completed = sum(1 for t in todos if t.get("status") == "completed")
        total = len(todos)
        return f"{completed}/{total} completed"

    def format_output_details(self, event: AgentToolOutputEvent) -> str | None:
        """Generate a formatted list of tasks with [x]/[~]/[ ] status markers."""
        todos = self._parse_todos()
        if not todos:
            return None

        lines: list[str] = []
        for todo in todos:
            status = todo.get("status", "pending")
            content = todo.get("content", "")
            active_form = todo.get("active_form", content)

            if status == "completed":
                lines.append(f"[x] {content}")
            elif status == "in_progress":
                lines.append(f"[~] {active_form}")
            else:  # pending
                lines.append(f"[ ] {content}")

        return "\n".join(lines)

    def _parse_todos(self) -> list[dict[str, Any]]:
        """Parse todos from the stored tool call arguments."""
        if self._last_call_event is None:
            return []
        try:
            args = json.loads(self._last_call_event.arguments)
            return args.get("todos", [])
        except (json.JSONDecodeError, TypeError):
            return []
