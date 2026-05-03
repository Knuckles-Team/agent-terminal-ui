#!/usr/bin/python
"""Rich-based formatters for the terminal event log.

Backward compatibility shim — these functions/classes are preserved
for any legacy code paths that still use Rich renderables directly.
The primary rendering path now uses Textual widgets from
agent_terminal_ui.widgets.

Concept: AU-018 (Backward Compatibility)
"""

from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import Markdown
from rich.segment import Segment
from rich.style import Style
from rich.text import Text

# Re-export from new location for backward compatibility
from agent_terminal_ui.widgets.utils import (
    AGENT_COLORS,
    format_agent_prefix,
    format_agent_prefix_markup,
    get_agent_color,
)

BULLET: str = "\u2022"

__all__ = [
    "AGENT_COLORS",
    "BULLET",
    "BulletMarkdown",
    "format_agent_prefix",
    "format_agent_prefix_markup",
    "format_user_message",
    "get_agent_color",
]


class BulletMarkdown:
    """Markdown content with a bullet prefix and optional styling.

    A custom Rich renderable that displays markdown text preceded by a
    consistent bullet point. Supports attribution to specific agents and
    dimming for secondary information.

    Note: This is a legacy renderable kept for backward compatibility.
    New code should use AgentResponse widget instead.
    """

    def __init__(
        self,
        content: str,
        *,
        dim: bool = False,
        show_bullet: bool = True,
        agent_name: str = "main",
    ) -> None:
        """Initialize the bulleted markdown renderable.

        Args:
            content: The raw markdown text to render.
            dim: Whether to render the content with a dimmed style.
            show_bullet: Whether to include the bullet point at the start.
            agent_name: The identifier of the agent to attribute the message to.
        """
        self.content = content
        self.dim = dim
        self.show_bullet = show_bullet
        self.agent_name = agent_name

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Rich protocol implementation for custom rendering."""
        style = Style(dim=True) if self.dim else Style()
        bullet_style = Style(color="bright_yellow", bold=True) + style

        if self.agent_name != "main":
            color = get_agent_color(self.agent_name)
            prefix_style = Style(color=color) + style
            prefix_text = f"({self.agent_name}) "
        else:
            prefix_style = None
            prefix_text = ""

        md = Markdown(self.content, style=style)
        render_options = options.update_width(options.max_width - 2)
        lines = console.render_lines(md, render_options)

        bullet = Segment(f"{BULLET} ", bullet_style)
        padding = Segment("  ", style)

        for i, line in enumerate(lines):
            if i == 0 and self.show_bullet:
                yield bullet
                if prefix_text:
                    yield Segment(prefix_text, prefix_style)
            else:
                yield padding
            yield from line
            yield Segment("\n")


def format_user_message(content: str) -> Text:
    """Format a user message with a blockquote style.

    Note: This is a legacy function kept for backward compatibility.
    New code should use UserMessage widget instead.

    Args:
        content: The raw message string from the user.

    Returns:
        A Rich Text object ready for display.
    """
    lines = content.split("\n")
    text = Text()
    for i, line in enumerate(lines):
        if i == 0:
            text.append("> ", style="bold blue")
            text.append(line)
        else:
            text.append("\n  ")
            text.append(line)
    return text
