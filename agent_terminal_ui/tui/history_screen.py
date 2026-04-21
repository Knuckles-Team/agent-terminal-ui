#!/usr/bin/python
"""Session history browser screen.

Provides a modal interface for viewing past conversation summaries and
selecting a session to resume in the terminal UI.
"""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label


class HistoryScreen(ModalScreen[str | None]):
    """Modal screen for browsing chat history and selecting a session.

    Displays a searchable table of past chat sessions with timestamps,
    unique identifiers, and message snippets.
    """

    DEFAULT_CSS: str = """
    HistoryScreen {
        align: center middle;
    }

    #history-dialog {
        width: 90%;
        height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }

    #history-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    """

    def __init__(self, chats: list[dict[str, Any]]) -> None:
        """Initialize the history screen with session data.

        Args:
            chats: A list of message history metadata dictionaries from the server.

        """
        super().__init__()
        self.chats: list[dict[str, Any]] = chats

    def compose(self) -> ComposeResult:
        """Construct the history dialog layout.

        Returns:
            A Textual ComposeResult containing title, table, and instructions.

        """
        with Vertical(id="history-dialog"):
            yield Label("[bold]Session History[/bold]", id="history-title")
            yield DataTable(id="history-table")
            yield Label(
                "Press [bold]Enter[/bold] to select, [bold]Esc[/bold] to cancel"
            )

    def on_mount(self) -> None:
        """Populate the history table when the screen is mounted."""
        table = self.query_one(DataTable)
        table.add_columns("Date", "ID", "Snippet")
        table.cursor_type = "row"

        for chat in self.chats:
            table.add_row(
                chat.get("timestamp", "N/A"),
                chat.get("id", "N/A"),
                chat.get("firstMessage", "N/A")[:80],
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle selection of a chat session row.

        Dismisses the modal and returns the selected chat identifier.

        Args:
            event: The Textual row selection event.

        """
        row_index = event.cursor_row
        chat_id = self.chats[row_index].get("id")
        self.dismiss(chat_id)

    def on_key(self, event: Any) -> None:
        """Handle key events to allow cancellation via the Escape key.

        Args:
            event: The Textual key event.

        """
        if event.key == "escape":
            self.dismiss(None)
