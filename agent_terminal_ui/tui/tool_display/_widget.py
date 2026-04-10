"""Rich renderables for displaying tool calls and outputs in RichLog."""

from agent_tui.tui.formatters import format_agent_prefix_markup
from rich.console import Console, ConsoleOptions, RenderResult
from rich.style import Style
from rich.text import Text

CONTINUATION_CHAR = "\u23bf"  # ⎿


class ToolCallDisplay:
    """Rich renderable for a tool call header line."""

    def __init__(
        self, header: str, *, pending: bool = True, agent_name: str = "main"
    ) -> None:
        self.header = header
        self.agent_name = agent_name
        self.pending = pending

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        text = Text()
        dot_style = "yellow" if self.pending else "green"
        text.append("\u25cb ", style=dot_style)
        prefix_markup = format_agent_prefix_markup(self.agent_name)
        if prefix_markup:
            text.append_text(Text.from_markup(prefix_markup))
        text.append(self.header, style="dim")
        yield text


class ToolOutputDisplay:
    """Rich renderable for combined tool call and output display."""

    def __init__(
        self,
        header: str,
        summary: str | None = None,
        details: str | None = None,
        *,
        success: bool = True,
        agent_name: str = "main",
    ) -> None:
        self.header = header
        self.agent_name = agent_name
        self.summary = summary
        self.details = details
        self.success = success

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        header_text = Text()
        header_text.append("\u25cf ", style="green")
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
