"""Structured conversation widget for the main chat interface.

Replaces the RichLog approach with a scrollable container of typed
message blocks (UserMessage, AgentResponse, ToolCallBlock, Throbber).
Each block is a proper Textual widget, enabling click interaction,
expansion, and structured styling.

Concept: AU-018 (Structured Conversation Architecture)
"""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.containers import VerticalGroup, VerticalScroll
from textual.widgets import Static

from agent_terminal_ui.widgets.agent_response import AgentResponse
from agent_terminal_ui.widgets.throbber import Throbber
from agent_terminal_ui.widgets.tool_call_block import ToolCallBlock
from agent_terminal_ui.widgets.user_message import UserMessage

logger = logging.getLogger(__name__)


class Window(VerticalGroup):
    """Inner container for conversation blocks.

    Holds the sequence of message widgets and manages auto-scrolling
    to keep the latest content visible.
    """

    DEFAULT_CSS = """
    Window {
        height: auto;
        padding: 1 0;
    }
    """


class Conversation(VerticalScroll):
    """Main conversation container with structured message blocks.

    This widget replaces the RichLog used previously. Instead of appending
    Rich renderables, it mounts typed Textual widgets that support
    interaction, styling, and structured layout.

    Features:
        - Auto-scrolling to bottom on new content
        - Streaming agent response updates
        - Expandable tool call blocks
        - Inline throbber for thinking state
    """

    DEFAULT_CSS = """
    Conversation {
        height: 1fr;
        background: $background;
        scrollbar-background: $background;
        scrollbar-color: $surface;
        scrollbar-color-hover: $text-muted;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the conversation widget.

        Args:
            name: Optional Textual name.
            id: Optional Textual id.
            classes: Optional Textual CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._current_response: AgentResponse | None = None
        self._throbber: Throbber | None = None
        self._tool_blocks: dict[str, ToolCallBlock] = {}

    def compose(self) -> ComposeResult:
        """Compose the conversation layout."""
        yield Window()

    @property
    def window(self) -> Window:
        """The inner window container."""
        return self.query_one(Window)

    async def add_welcome(self, logo: str) -> None:
        """Add a welcome message to the conversation.

        Args:
            logo: The welcome text/logo to display.
        """
        await self.window.mount(Static(logo, classes="welcome-banner", markup=True))
        self._prune_old_widgets()
        self.scroll_end(animate=False)

    async def add_user_message(self, content: str) -> None:
        """Add a user message block to the conversation.

        Args:
            content: The user's input text.
        """
        self._finalize_current_response()
        widget = UserMessage(content)
        await self.window.mount(widget)
        self._prune_old_widgets()
        self.scroll_end(animate=False)

    async def add_agent_response(self, content: str, agent_name: str = "main") -> None:
        """Add a complete agent response to the conversation.

        For streaming, use `start_agent_response()` and `append_to_response()`.

        Args:
            content: The full markdown content.
            agent_name: The agent identifier.
        """
        self._finalize_current_response()
        widget = AgentResponse(content, agent_name=agent_name)
        await self.window.mount(widget)
        self._current_response = None
        self._prune_old_widgets()
        self.scroll_end(animate=False)

    async def start_agent_response(self, agent_name: str = "main") -> None:
        """Begin a new streaming agent response.

        Args:
            agent_name: The agent identifier.
        """
        self._finalize_current_response()
        widget = AgentResponse("", agent_name=agent_name)
        await self.window.mount(widget)
        self._current_response = widget
        self._prune_old_widgets()
        self.scroll_end(animate=False)

    async def append_to_response(self, delta: str) -> None:
        """Append streaming content to the current agent response.

        Args:
            delta: The text chunk to append.
        """
        if self._current_response is not None:
            await self._current_response.append_content(delta)
            self.scroll_end(animate=False)
        else:
            # No active response — start a new one
            await self.start_agent_response()
            if self._current_response is not None:
                await self._current_response.append_content(delta)

    async def add_tool_call(
        self,
        tool_name: str,
        tool_args: str = "",
        *,
        status: str = "pending",
        agent_name: str = "main",
        call_id: str = "",
        content: str | None = None,
        details: str | None = None,
    ) -> None:
        """Add a tool call block to the conversation.

        Args:
            tool_name: Name of the tool.
            tool_args: Formatted arguments.
            status: Current status.
            agent_name: Agent making the call.
            call_id: Unique call identifier.
            content: Optional output content.
            details: Optional detailed output.
        """
        self._finalize_current_response()
        block = ToolCallBlock(
            tool_name,
            tool_args,
            status=status,
            agent_name=agent_name,
            call_id=call_id,
            content=content,
            details=details,
        )
        self._tool_blocks[call_id] = block
        await self.window.mount(block)
        self._prune_old_widgets()
        self.scroll_end(animate=False)

    async def update_tool_call(
        self,
        call_id: str,
        *,
        status: str | None = None,
        content: str | None = None,
        details: str | None = None,
    ) -> None:
        """Update an existing tool call block.

        Args:
            call_id: The tool call identifier.
            status: New status.
            content: New content.
            details: New details.
        """
        block = self._tool_blocks.get(call_id)
        if block is not None:
            await block.update_tool_call(
                status=status, content=content, details=details
            )
            self.scroll_end(animate=False)

    async def add_info(self, text: str) -> None:
        """Add an informational message to the conversation.

        Args:
            text: The info text (supports Rich markup).
        """
        self._finalize_current_response()
        await self.window.mount(Static(text, classes="info-message", markup=True))
        self._prune_old_widgets()
        self.scroll_end(animate=False)

    async def add_error(self, text: str) -> None:
        """Add an error message to the conversation.

        Args:
            text: The error text.
        """
        self._finalize_current_response()
        await self.window.mount(
            Static(
                f"[$error]Error: {text}[/$error]",
                classes="error-message",
                markup=True,
            )
        )
        self._prune_old_widgets()
        self.scroll_end(animate=False)

    def start_thinking(self, label: str = "Thinking") -> None:
        """Show the throbber in the conversation.

        Args:
            label: The label text for the throbber.
        """
        if self._throbber is None:
            self._throbber = Throbber(label, id="conversation-throbber")
            self.window.mount(self._throbber)
        self._throbber.start(label)
        self.scroll_end(animate=False)

    def stop_thinking(self) -> None:
        """Stop and hide the throbber."""
        if self._throbber is not None:
            self._throbber.stop()

    async def clear_conversation(self) -> None:
        """Remove all content from the conversation."""
        self._finalize_current_response()
        self._tool_blocks.clear()
        if self._throbber is not None:
            self._throbber.stop()
            self._throbber = None
        await self.window.remove_children()

    def _finalize_current_response(self) -> None:
        """Finalize any in-progress streaming response."""
        self._current_response = None

    def _prune_old_widgets(self) -> None:
        """Prune older message widgets to maintain a lightweight DOM."""
        try:
            max_widgets = self.app.settings.get("max_conversation_widgets", 50)
        except Exception:
            max_widgets = 50

        # Gather eligible children for pruning
        children = list(self.window.children)
        eligible = []
        for child in children:
            if child is self._throbber:
                continue
            if child is self._current_response:
                continue
            eligible.append(child)

        # If we exceed the limit, remove the oldest ones
        excess = len(eligible) - max_widgets
        if excess > 0:
            for i in range(excess):
                widget_to_remove = eligible[i]
                # If it's a tool block, also remove it from our active tool blocks map
                for call_id, block in list(self._tool_blocks.items()):
                    if block is widget_to_remove:
                        self._tool_blocks.pop(call_id, None)
                widget_to_remove.remove()
