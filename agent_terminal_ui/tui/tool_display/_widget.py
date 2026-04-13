#!/usr/bin/python
# coding: utf-8
"""Rich renderables for tool display widgets.

This module defines custom Rich renderable objects used to display tool
call headers and their corresponding outputs (summaries and details)
within the Textual RichLog event log.
"""

from rich.console import Console, ConsoleOptions, RenderResult
from rich.style import Style
from rich.text import Text

from agent_terminal_ui.tui.formatters import format_agent_prefix_markup

CONTINUATION_CHAR: str = "\u23bf"  # ⎿


class ToolCallDisplay:
    """Rich renderable for a tool call initialization header.

    Displays an open circle indicator and the tool name with arguments,
    optionally including the identifier of the agent initiating the call.
    """

    def __init__(
        self, header: str, *, pending: bool = True, agent_name: str = "main"
    ) -> None:
        """Initialize the tool call display object.

        Args:
            header: The formatted tool name and arguments.
            pending: Whether the tool is waiting for execution or approval.
            agent_name: The identifier of the agent making the call.

        """
        self.header: str = header
        self.agent_name: str = agent_name
        self.pending: bool = pending

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Rich protocol implementation for rendering the header line."""
        text = Text()
        dot_style = "yellow" if self.pending else "green"
        text.append("\u25cb ", style=dot_style)
        prefix_markup = format_agent_prefix_markup(self.agent_name)
        if prefix_markup:
            text.append_text(Text.from_markup(prefix_markup))
        text.append(self.header, style="dim")
        yield text


class ToolOutputDisplay:
    """Rich renderable for displaying tool execution results.

    Displays a solid circle indicator followed by the tool header,
    an optional one-line summary, and indented execution details.
    """

    def __init__(
        self,
        header: str,
        summary: str | None = None,
        details: str | None = None,
        *,
        success: bool = True,
        agent_name: str = "main",
    ) -> None:
        """Initialize the tool output display object.

        Args:
            header: The formatted tool name and arguments.
            summary: A concise overview of the results (e.g., '15 lines read').
            details: Detailed output content (e.g., file contents or diff).
            success: Whether the tool executed without critical failure.
            agent_name: The identifier of the agent that used the tool.

        """
        self.header: str = header
        self.agent_name: str = agent_name
        self.summary: str | None = summary
        self.details: str | None = details
        self.success: bool = success

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Rich protocol implementation for rendering the output block."""
        header_text = Text()
        header_text.append("\u25cf ", style="green" if self.success else "red")
        prefix_markup = format_agent_prefix_markup(self.agent_name)
        if prefix_markup:
            header_text.append_text(Text.from_markup(prefix_markup))
        header_text.append(self.header)
        yield header_text

        dim_style = Style(dim=True)

        if self.summary:
            text = Text()
            text.append(f" {CONTINUATION_CHAR}  ", style=dim_style)
            text.append(self.summary, style=dim_style)
            yield text

        if self.details:
            for line in self.details.split("\n"):
                detail_text = Text()
                detail_text.append("    ", style=dim_style)  # 4-space indent
                detail_text.append(line, style=dim_style)
                yield detail_text
