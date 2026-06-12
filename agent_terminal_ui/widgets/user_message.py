"""User message widget for the conversation view.

Renders user input with blockquote-style formatting as a proper
Textual widget instead of a Rich renderable appended to RichLog.

Concept: AU-018 (Structured Conversation Blocks)
"""

from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Static

from agent_terminal_ui.tui.animation import animate_in


class UserMessage(HorizontalGroup):
    """A structured widget representing a user message in the conversation.

    Displays the user's input with a '>' prefix and primary accent color,
    preserving the original text without markdown parsing.
    """

    DEFAULT_CSS = """
    UserMessage {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
        background: $primary 8%;
        border-left: thick $primary;
    }

    UserMessage .user-prefix {
        width: 2;
        color: $primary;
        text-style: bold;
    }

    UserMessage .user-content {
        width: 1fr;
        color: $text;
        text-style: bold;
    }
    """

    def on_mount(self) -> None:
        """Animate the message into view."""
        animate_in(self)

    def __init__(
        self,
        content: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the user message widget.

        Args:
            content: The raw user message text.
            name: Optional Textual name.
            id: Optional Textual id.
            classes: Optional Textual CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._content = content

    def compose(self) -> ComposeResult:
        """Compose the user message layout."""
        yield Static("> ", classes="user-prefix", markup=False)
        yield Static(self._content, classes="user-content", markup=False)
