from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label


class HistoryScreen(ModalScreen[str | None]):
    """Screen for browsing chat history and selecting a session."""

    DEFAULT_CSS = """
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

    def __init__(self, chats: list[dict[str, Any]]):
        super().__init__()
        self.chats = chats

    def compose(self) -> ComposeResult:
        with Vertical(id="history-dialog"):
            yield Label("[bold]Session History[/bold]", id="history-title")
            yield DataTable(id="history-table")
            yield Label(
                "Press [bold]Enter[/bold] to select, [bold]Esc[/bold] to cancel"
            )

    def on_mount(self) -> None:
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
        """Handle row selection to return the chat ID."""
        row_index = event.cursor_row
        chat_id = self.chats[row_index].get("id")
        self.dismiss(chat_id)

    def on_key(self, event: Any) -> None:
        if event.key == "escape":
            self.dismiss(None)
