from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label


class MCPScreen(ModalScreen):
    """Screen for browsing configured MCP servers and their available tools."""

    DEFAULT_CSS = """
    MCPScreen {
        align: center middle;
    }

    #mcp-dialog {
        width: 80%;
        height: 70%;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }

    #mcp-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    DataTable {
        height: 1fr;
    }
    """

    def __init__(self, mcp_config: dict[str, Any], mcp_tools: list[dict[str, Any]]):
        super().__init__()
        self.mcp_config = mcp_config
        self.mcp_tools = mcp_tools or []

    def compose(self) -> ComposeResult:
        with Vertical(id="mcp-dialog"):
            yield Label("[bold]MCP Ecosystem Status[/bold]", id="mcp-title")
            yield Label(
                f"Configured Servers: {len(self.mcp_config.get('mcpServers', {}))}"
            )

            yield DataTable(id="tools-table")
            yield Label("Press [bold]Esc[/bold] to return")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Tool ID", "Name", "Description")

        for tool in self.mcp_tools:
            table.add_row(
                tool.get("id", "N/A"),
                tool.get("name", "N/A"),
                tool.get("description", "N/A")[:100],
            )

    def action_close(self) -> None:
        self.dismiss()

    def on_key(self, event: Any) -> None:
        if event.key == "escape":
            self.dismiss()
