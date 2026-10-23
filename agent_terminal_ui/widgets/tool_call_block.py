"""Expandable tool call block widget.

Replaces the flat ToolCallDisplay/ToolOutputDisplay Rich renderables with
a proper Textual widget that supports click-to-expand, status badges,
and auto-expand rules. Modeled after Toad's ToolCall widget.

Concept: AU-018 (Structured Conversation Blocks)
"""

from __future__ import annotations

from typing import ClassVar

from rich.markup import escape
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalGroup
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import var
from textual.widgets import Markdown, Static

from agent_terminal_ui.display_text import display_text
from agent_terminal_ui.widgets.utils import get_agent_color


class ToolCallHeader(Static):
    """Clickable header for a tool call block."""

    ALLOW_SELECT = False
    can_focus = True
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter,space", "toggle_section", "Expand/collapse", show=False),
    ]

    class Toggle(Message):
        """An explicit keyboard request to change this fold."""

    def action_toggle_section(self) -> None:
        self.post_message(self.Toggle())

    DEFAULT_CSS = """
    ToolCallHeader {
        width: 1fr;
        height: auto;
        padding: 0 1;
        &:focus {
            background: $surface;
            text-style: bold;
        }
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
        self._tool_name = display_text(tool_name, multiline=False)
        self._tool_args = display_text(tool_args, multiline=False)
        self._status = status
        self._agent_name = display_text(agent_name, multiline=False)
        self._call_id = call_id
        self._content = display_text(content) if content is not None else None
        self._details = display_text(details) if details is not None else None
        self._user_toggled = False
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
            agent_prefix = f"[{color}]({escape(self._agent_name)})[/{color}] "

        # Tool display
        tool_display = escape(self._tool_name)
        if self._tool_args:
            tool_display += " " + escape(f"[{self._tool_args}]")

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
            yield Markdown(self._content or "", open_links=False)
            yield Static(self._details or "", classes="tool-details", markup=False)

    def on_mount(self) -> None:
        """Animate the tool call block into view."""
        from agent_terminal_ui.tui.animation import animate_in

        animate_in(self)
        self._sync_content_visibility()
        self._apply_expansion_policy()
        self.watch_expanded()

    def _sync_content_visibility(self) -> None:
        self.query_one(Markdown).display = bool(self._content)
        self.query_one(".tool-details", Static).display = bool(self._details)

    def _apply_expansion_policy(self) -> None:
        if self._user_toggled or not self.has_content:
            return
        settings = getattr(self.app, "settings", {})
        mode = settings.get("tool_expand", "on-fail")
        if (
            mode == "always"
            or (mode == "on-fail" and self.status == "failed")
            or (mode == "on-success" and self.status == "completed")
        ):
            self.expanded = True

    def _toggle(self) -> None:
        if self.has_content:
            self._user_toggled = True
            self.expanded = not self.expanded
        else:
            self.app.bell()

    @on(ToolCallHeader.Toggle)
    def _on_header_toggle(self, event: ToolCallHeader.Toggle) -> None:
        event.stop()
        self._toggle()

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
        self.query_one(ToolCallHeader).focus()
        self._toggle()

    async def update_tool_call(
        self,
        *,
        status: str | None = None,
        content: str | None = None,
        details: str | None = None,
    ) -> None:
        """Update mounted content and status without replacing focused widgets.

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
            self._content = display_text(content)

        if details is not None:
            self._details = display_text(details)

        self.has_content = bool(self._content or self._details)
        if self.is_mounted:
            if content is not None:
                await self.query_one(Markdown).update(self._content or "")
            if details is not None:
                self.query_one(".tool-details", Static).update(self._details or "")
            self._sync_content_visibility()
            self._apply_expansion_policy()

        # Update header
        try:
            header = self.query_one(ToolCallHeader)
            header.update(self._build_header_text())
        except NoMatches:
            pass
