#!/usr/bin/python
"""Chat Modal Screen.

Provides a ModalScreen to display communication messages between agents
within a specific subgraph or workflow node.
"""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, RichLog


class ChatModal(ModalScreen[None]):
    """Modal to display chat messages for a subgraph."""

    DEFAULT_CSS = """
    ChatModal {
        align: center middle;
        background: $background 50%;
    }

    #chat-dialog {
        width: 80;
        height: 80%;
        background: $surface;
        border: tall $primary;
        padding: 1 2;
    }

    #chat-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
        width: 100%;
    }

    #chat-log {
        height: 1fr;
        border: solid $border;
        background: $background;
        padding: 1;
    }

    #close-btn {
        margin-top: 1;
        align-horizontal: center;
    }
    """

    def __init__(self, title: str, messages: list[dict[str, str]]) -> None:
        """Initialize the chat modal.

        Args:
            title: Title to display in the modal header.
            messages: List of message dicts with 'sender' and 'content'.
        """
        super().__init__()
        self.title_text = title
        self.messages = messages

    def compose(self) -> ComposeResult:
        """Compose the modal UI."""
        with Vertical(id="chat-dialog"):
            yield Label(self.title_text, id="chat-title")
            yield RichLog(id="chat-log", wrap=True)
            yield Button("Close", id="close-btn", variant="error")

    def on_mount(self) -> None:
        """Populate the chat log on mount."""
        log = self.query_one("#chat-log", RichLog)
        for msg in self.messages:
            sender = msg.get("sender", "unknown")
            content = msg.get("content", "")
            log.write(f"[bold cyan]{sender}:[/bold cyan] {content}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "close-btn":
            self.dismiss()
