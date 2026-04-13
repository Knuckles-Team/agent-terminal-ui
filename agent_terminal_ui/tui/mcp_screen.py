#!/usr/bin/python
# coding: utf-8
"""MCP Ecosystem browser screen.

Provides a modal interface for viewing configured Model Context Protocol (MCP)
servers and the combined toolset available to the agent cluster.
"""

from typing import Any
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label


class MCPScreen(ModalScreen[None]):
    """Modal screen for browsing configured MCP servers and their available tools.

    Displays an overview of the server configuration and a detailed table
    of all tools discovered across the ecosystem, including their
    descriptions and identifiers.
    """

    DEFAULT_CSS: str = """
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

    def __init__(
        self, mcp_config: dict[str, Any], mcp_tools: list[dict[str, Any]]
    ) -> None:
        """Initialize the MCP screen with configuration and tool data.

        Args:
            mcp_config: The server's MCP configuration dictionary.
            mcp_tools: A list of tool definition dictionaries.

        """
        super().__init__()
        self.mcp_config: dict[str, Any] = mcp_config
        self.mcp_tools: list[dict[str, Any]] = mcp_tools or []

    def compose(self) -> ComposeResult:
        """Construct the MCP dialog layout.

        Returns:
            A Textual ComposeResult containing title, stats, and tools table.

        """
        with Vertical(id="mcp-dialog"):
            yield Label("[bold]MCP Ecosystem Status[/bold]", id="mcp-title")
            yield Label(
                f"Configured Servers: {len(self.mcp_config.get('mcpServers', {}))}"
            )

            yield DataTable(id="tools-table")
            yield Label("Press [bold]Esc[/bold] to return")

    def on_mount(self) -> None:
        """Populate the tools table when the screen is mounted."""
        table = self.query_one(DataTable)
        table.add_columns("Tool ID", "Name", "Description")

        for tool in self.mcp_tools:
            table.add_row(
                tool.get("id", "N/A"),
                tool.get("name", "N/A"),
                tool.get("description", "N/A")[:100],
            )

    def action_close(self) -> None:
        """Dismiss the modal screen."""
        self.dismiss()

    def on_key(self, event: Any) -> None:
        """Handle key events to allow exiting via the Escape key.

        Args:
            event: The Textual key event.

        """
        if event.key == "escape":
            self.dismiss()
