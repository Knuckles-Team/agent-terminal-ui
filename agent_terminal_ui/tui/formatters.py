from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import Markdown
from rich.segment import Segment
from rich.style import Style
from rich.text import Text

BULLET = "\u2022"

# Muted/pastel colors for subagents
AGENT_COLORS = [
    "#9db4c0",  # pale blue
    "#c9ada7",  # pale mauve
    "#a7c4a0",  # pale green
    "#d4a5a5",  # pale rose
    "#b8a9c9",  # pale lavender
    "#f0d9b5",  # pale peach
    "#87bdd8",  # soft blue
    "#d5c4a1",  # pale khaki
]


def get_agent_color(agent_name: str) -> str:
    """Return a consistent color for an agent based on its name."""
    return AGENT_COLORS[hash(agent_name) % len(AGENT_COLORS)]


def format_agent_prefix(agent_name: str) -> str:
    """Return agent name prefix for display, empty string for main agent."""
    if agent_name == "main":
        return ""
    return f"({agent_name}) "


def format_agent_prefix_markup(agent_name: str) -> str:
    """Return agent name prefix with Rich markup color, empty string for main agent."""
    if agent_name == "main":
        return ""
    color = get_agent_color(agent_name)
    return f"[{color}]({agent_name})[/{color}] "


class BulletMarkdown:
    """Markdown content with a bullet prefix and optional dim styling."""

    def __init__(
        self,
        content: str,
        *,
        dim: bool = False,
        show_bullet: bool = True,
        agent_name: str = "main",
    ) -> None:
        self.content = content
        self.dim = dim
        self.show_bullet = show_bullet
        self.agent_name = agent_name

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        style = Style(dim=True) if self.dim else Style()
        bullet_style = Style(color="bright_yellow", bold=True) + style

        # Render agent prefix with color if not main
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
    """Format user message with > prefix, no markdown."""
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
