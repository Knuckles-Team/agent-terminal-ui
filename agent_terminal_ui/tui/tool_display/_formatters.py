import json
from typing import Any, Protocol

from agent_core._types import AgentToolCallEvent, AgentToolOutputEvent


class ToolDisplayFormatter(Protocol):
    """Protocol for formatting tool calls and outputs for display."""

    def format_call_header(self, event: AgentToolCallEvent) -> str:
        """Format the tool call header line.

        Example: "Update(/home/david/repos/agent-core/src/agent_core/app.py)"
        """
        ...

    def format_output_summary(self, event: AgentToolOutputEvent) -> str | None:
        """Format a one-line summary of the tool output.

        Example: "Removed 2 lines"
        Returns None if no summary should be shown.
        """
        ...

    def format_output_details(self, event: AgentToolOutputEvent) -> str | None:
        """Format detailed output (e.g., diff view, file contents).

        Returns None if no details should be shown.
        """
        ...


class DefaultToolDisplayFormatter:
    """Default formatter that works for any tool."""

    def format_call_header(self, event: AgentToolCallEvent) -> str:
        args = self._parse_arguments(event.arguments)
        primary = self._find_primary_param(args)
        if primary:
            return f"{event.name}({primary})"
        params_str = ", ".join(f"{k}={self._truncate(v)}" for k, v in args.items())
        return f"{event.name}({params_str})"

    def format_output_summary(self, event: AgentToolOutputEvent) -> str | None:
        result = self._get_result(event.output)
        if not result:
            return "Completed"
        line_count = result.count("\n") + 1
        return f"{line_count} lines" if line_count > 1 else "1 line"

    def format_output_details(self, event: AgentToolOutputEvent) -> str | None:
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
        if not arguments:
            return {}
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return {}

    def _find_primary_param(self, args: dict[str, Any]) -> str | None:
        for key in ("file_path", "path", "command", "pattern"):
            if key in args:
                return str(args[key])
        return None

    def _truncate(self, value: Any, max_len: int = 50) -> str:
        s = str(value)
        return s if len(s) <= max_len else s[:max_len] + "..."

    def _get_result(self, output: dict[str, Any]) -> str:
        result = output.get("result", "")
        return result if isinstance(result, str) else ""


class EditToolFormatter:
    """Custom formatter for edit tool calls."""

    display_name = "Update"

    def format_call_header(self, event: AgentToolCallEvent) -> str:
        args = self._parse_arguments(event.arguments)
        file_path = args.get("file_path", "unknown")
        return f"{self.display_name}({file_path})"

    def format_output_summary(self, event: AgentToolOutputEvent) -> str | None:
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
        return self._get_result(event.output) or None

    def _parse_arguments(self, arguments: str) -> dict[str, Any]:
        if not arguments:
            return {}
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return {}

    def _count_changes(self, result: str) -> tuple[int, int]:
        added = result.count("\n+")
        removed = result.count("\n-")
        return added, removed

    def _get_result(self, output: dict[str, Any]) -> str:
        result = output.get("result", "")
        return result if isinstance(result, str) else ""


class TodoToolFormatter:
    """Custom formatter for todo_write tool calls."""

    display_name = "Todos"

    def __init__(self) -> None:
        self._last_call_event: AgentToolCallEvent | None = None

    def format_call_header(self, event: AgentToolCallEvent) -> str:
        self._last_call_event = event
        return self.display_name

    def format_output_summary(self, event: AgentToolOutputEvent) -> str | None:
        todos = self._parse_todos()
        if not todos:
            return None
        completed = sum(1 for t in todos if t.get("status") == "completed")
        total = len(todos)
        return f"{completed}/{total} completed"

    def format_output_details(self, event: AgentToolOutputEvent) -> str | None:
        todos = self._parse_todos()
        if not todos:
            return None

        lines = []
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
