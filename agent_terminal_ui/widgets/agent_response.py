"""Agent response widget with streaming Markdown rendering.

Renders agent output as live Markdown using Textual's Markdown widget,
supporting code fences, tables, lists, and inline formatting. Replaces
the BulletMarkdown Rich renderable with a proper widget.

Concept: AU-018 (Structured Conversation Blocks)
"""

from textual.app import ComposeResult
from textual.containers import VerticalGroup
from textual.widgets import Markdown, Static

from agent_terminal_ui.tui.animation import animate_in
from agent_terminal_ui.widgets.utils import get_agent_color


class AgentResponse(VerticalGroup):
    """A structured widget for displaying agent responses with Markdown.

    Supports streaming updates via `append_content()` for live rendering
    of agent text as it arrives. Optionally displays an agent name prefix
    for multi-agent scenarios.
    """

    DEFAULT_CSS = """
    AgentResponse {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
        background: $boost;
        border-left: thick $success 60%;
    }

    AgentResponse .agent-prefix {
        height: 1;
        margin: 0 0 0 0;
        text-style: bold;
    }

    AgentResponse .agent-markdown {
        height: auto;
        margin: 0 0 0 2;
    }
    """

    def on_mount(self) -> None:
        """Animate the response into view."""
        animate_in(self)

    def __init__(
        self,
        content: str = "",
        *,
        agent_name: str = "main",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the agent response widget.

        Args:
            content: Initial markdown content (can be empty for streaming).
            agent_name: The agent identifier for prefix attribution.
            name: Optional Textual name.
            id: Optional Textual id.
            classes: Optional Textual CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._content = content
        self._agent_name = agent_name

    def compose(self) -> ComposeResult:
        """Compose the agent response layout."""
        if self._agent_name != "main":
            color = get_agent_color(self._agent_name)
            yield Static(
                f"[{color}]● {self._agent_name}[/{color}]",
                classes="agent-prefix",
                markup=True,
            )
        else:
            yield Static(
                "[$text-success]●[/$text-success] agent",
                classes="agent-prefix",
                markup=True,
            )
        yield Markdown(self._content, classes="agent-markdown")

    @property
    def content(self) -> str:
        """The current full content of the response."""
        return self._content

    async def append_content(self, delta: str) -> None:
        """Append streaming content to the response.

        Args:
            delta: The new text chunk to add.
        """
        self._content += delta
        try:
            md_widget = self.query_one(".agent-markdown", Markdown)
            await md_widget.update(self._content)
        except Exception:  # nosec B110
            pass

    async def update_content(self, content: str) -> None:
        """Replace the entire content of the response.

        Args:
            content: The complete new content.
        """
        self._content = content
        try:
            md_widget = self.query_one(".agent-markdown", Markdown)
            await md_widget.update(self._content)
        except Exception:  # nosec B110
            pass
