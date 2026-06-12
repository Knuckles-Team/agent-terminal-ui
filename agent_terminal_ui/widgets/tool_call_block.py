"""Expandable tool call block widget.

Replaces the flat ToolCallDisplay/ToolOutputDisplay Rich renderables with
a proper Textual widget that supports click-to-expand, status badges,
and auto-expand rules. Modeled after Toad's ToolCall widget.

Concept: AU-018 (Structured Conversation Blocks)
"""

from __future__ import annotations

from textual import events, on
from textual.app import ComposeResult
from textual.containers import VerticalGroup
from textual.css.query import NoMatches
from textual.reactive import var
from textual.widgets import Markdown, Static

from agent_terminal_ui.widgets.utils import get_agent_color


class ToolCallHeader(Static):
    """Clickable header for a tool call block."""

    ALLOW_SELECT = False
    DEFAULT_CSS = """
    ToolCallHeader {
        width: 1fr;
        height: auto;
        padding: 0 1;
        &:hover {
            background: $surface;
        }
    }
    """


class ToolCallContent(VerticalGroup):
    """Container for tool call output content."""

    DEFAULT_CSS = """
    ToolCallContent {
        height: auto;
        padding: 0 1 0 3;
        display: none;
    }

    ToolCallContent.-visible {
        display: block;
    }
    """


class ToolCallBlock(VerticalGroup):
    """An expandable/collapsible tool call display.

    Shows a header with tool name, status badge, and expand/collapse icon.
    Clicking the header toggles the content visibility. Supports auto-expand
    rules configured via settings.

    Attributes:
        expanded: Whether the content section is currently visible.
        has_content: Whether there is any content to show.
    """

    DEFAULT_CSS = """
    ToolCallBlock {
        height: auto;
        margin: 0 0 1 0;
        border-left: tall $primary;
        padding: 0;
    }

    ToolCallBlock.-failed {
        border-left: tall $error;
    }

    ToolCallBlock.-completed {
        border-left: tall $success;
    }

    ToolCallBlock.-pending {
        border-left: tall $warning;
    }
    """

    expanded: var[bool] = var(False)
    has_content: var[bool] = var(False)

    def __init__(
        self,
        tool_name: str,
        tool_args: str = "",
        *,
        status: str = "pending",
        agent_name: str = "main",
        call_id: str = "",
        content: str | None = None,
        details: str | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the tool call block.

        Args:
            tool_name: Name of the tool being called.
            tool_args: Formatted arguments string.
            status: Current status (pending, in_progress, completed, failed).
            agent_name: The agent making the call.
            call_id: Unique call identifier.
            content: Optional content to display when expanded.
            details: Optional detailed output text.
            name: Optional Textual name.
            id: Optional Textual id.
            classes: Optional Textual CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._tool_name = tool_name
        self._tool_args = tool_args
        self._status = status
        self._agent_name = agent_name
        self._call_id = call_id
        self._content = content
        self._details = details
        self.has_content = bool(content or details)

    @property
    def status(self) -> str:
        """Current status of the tool call."""
        return self._status

    def _build_header_text(self) -> str:
        """Build the header content string with status badge."""
        # Expand/collapse indicator
        indicator = "▼" if self.expanded else "▶"
        dim = "" if self.has_content else " dim"

        # Status badge
        status_badge = ""
        if self._status == "pending":
            status_badge = " ⌛"
        elif self._status == "completed":
            status_badge = " [$success]✔[/$success]"
        elif self._status == "failed":
            status_badge = " [$error]✕ failed[/$error]"
        elif self._status == "in_progress":
            status_badge = " [$warning]…[/$warning]"

        # Agent prefix
        agent_prefix = ""
        if self._agent_name != "main":
            color = get_agent_color(self._agent_name)
            agent_prefix = f"[{color}]({self._agent_name})[/{color}] "

        # Tool display
        tool_display = self._tool_name
        if self._tool_args:
            tool_display += f" [{self._tool_args}]"

        return (
            f"[$text-muted{dim}]{indicator}[/$text-muted{dim}] "
            f"🔧 {agent_prefix}{tool_display}{status_badge}"
        )

    def compose(self) -> ComposeResult:
        """Compose the tool call block layout."""
        self.set_class(self._status == "failed", "-failed")
        self.set_class(self._status == "completed", "-completed")
        self.set_class(self._status == "pending", "-pending")

        yield ToolCallHeader(self._build_header_text(), markup=True)
        with ToolCallContent():
            if self._content:
                yield Markdown(self._content)
            if self._details:
                yield Static(self._details, classes="tool-details", markup=False)

    def on_mount(self) -> None:
        """Animate the tool call block into view."""
        from agent_terminal_ui.tui.animation import animate_in

        animate_in(self)

    def watch_expanded(self) -> None:
        """React to expansion state changes."""
        try:
            content = self.query_one(ToolCallContent)
            content.set_class(self.expanded, "-visible")
            header = self.query_one(ToolCallHeader)
            header.update(self._build_header_text())
        except NoMatches:
            pass

    @on(events.Click, "ToolCallHeader")
    def _on_header_click(self, event: events.Click) -> None:
        """Toggle expansion when header is clicked."""
        event.stop()
        if self.has_content:
            self.expanded = not self.expanded
        else:
            self.app.bell()

    async def update_tool_call(
        self,
        *,
        status: str | None = None,
        content: str | None = None,
        details: str | None = None,
    ) -> None:
        """Update the tool call state and recompose.

        Args:
            status: New status value.
            content: New content to display.
            details: New details text.
        """
        if status is not None:
            self._status = status
            self.set_class(status == "failed", "-failed")
            self.set_class(status == "completed", "-completed")
            self.set_class(status == "pending", "-pending")

        if content is not None:
            self._content = content
            self.has_content = True

        if details is not None:
            self._details = details
            self.has_content = True

        # Update header
        try:
            header = self.query_one(ToolCallHeader)
            header.update(self._build_header_text())
        except NoMatches:
            pass

        # Auto-expand on completion/failure if content exists
        if self.has_content and status in ("completed", "failed"):
            self.expanded = True
