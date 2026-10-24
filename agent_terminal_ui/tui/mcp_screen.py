#!/usr/bin/python
"""MCP Ecosystem browser screen.

Provides a modal interface for viewing configured Model Context Protocol (MCP)
servers and the combined toolset available to the agent cluster.
"""

from typing import Any

import httpx
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label, Static
from textual.worker import get_current_worker

from agent_terminal_ui.client import AgentClient, ArboraOperationError


class MCPScreen(ModalScreen[None]):
    """Modal screen for browsing configured MCP servers and their available tools.

    Displays an overview of the server configuration and a detailed table
    of all tools discovered across the ecosystem, including their
    descriptions and identifiers.
    """

    BINDINGS = [("escape", "close", "Close"), ("r", "refresh", "Refresh")]

    DEFAULT_CSS: str = """
    MCPScreen {
        align: center middle;
    }

    #mcp-dialog {
        width: 90%;
        height: 90%;
        min-height: 10;
        max-height: 100%;
        background: $surface;
        border: thick $primary;
        padding: 0 1;
    }

    #mcp-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 0;
    }

    #tools-table {
        height: 1fr;
        min-height: 0;
    }
    """

    def __init__(
        self,
        mcp_config: dict[str, Any] | None = None,
        mcp_tools: list[dict[str, Any]] | None = None,
        *,
        client: AgentClient | None = None,
    ) -> None:
        """Initialize static data or load through the owning application client."""
        super().__init__()
        self.client = client
        self.mcp_config = mcp_config or {}
        self.mcp_tools = mcp_tools or []
        self._read_closed = False

    def compose(self) -> ComposeResult:
        """Construct the MCP dialog layout.

        Returns:
            A Textual ComposeResult containing title, stats, and tools table.

        """
        with Vertical(id="mcp-dialog"):
            yield Label("[bold]MCP Ecosystem Status[/bold]", id="mcp-title")
            yield Static("Loading MCP status...", id="mcp-status", markup=False)

            yield DataTable(id="tools-table")
            yield Label("R: refresh | Esc: close")

    def on_mount(self) -> None:
        """Populate the tools table when the screen is mounted."""
        table = self.query_one(DataTable)
        table.add_columns("Tool ID", "Name", "Description")

        if self.client is not None:
            self.action_refresh()
        else:
            self._render_data()

    def _render_data(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        self.query_one("#mcp-status", Static).update(
            f"Visible Servers: {len(self.mcp_config.get('children', {}))}"
            + (" | No tools available." if not self.mcp_tools else "")
        )
        for tool in self.mcp_tools:
            table.add_row(
                Text(tool.get("id", "N/A")),
                Text(tool.get("name", "N/A")),
                Text(tool.get("description", "N/A")[:100]),
            )

    @work(exclusive=True)
    async def action_refresh(self) -> None:
        """Read fresh fleet data without blocking close or retaining stale rows."""
        client = self.client
        if client is None or self._read_closed:
            return
        worker = get_current_worker()
        self.mcp_config = {}
        self.mcp_tools = []
        self.query_one(DataTable).clear()
        status = self.query_one("#mcp-status", Static)
        status.update("Loading fleet.status / fleet.catalog.list...")

        def current() -> bool:
            if worker.is_cancelled or self._read_closed or not self.is_mounted:
                return False
            if getattr(self.app, "_client", None) is not client:
                status.update("MCP unavailable: client changed. Close and reopen.")
                return False
            return True

        if not current():
            return
        try:
            config = await client.get_mcp_config()
            if not current():
                return
            tools = await client.list_mcp_tools()
            if not current():
                return
            self.mcp_config = config
            self.mcp_tools = tools
            self._render_data()
        except (ArboraOperationError, httpx.HTTPError, ValueError) as exc:
            if current():
                status.update(
                    f"MCP unavailable: fleet.status / fleet.catalog.list ({exc})"
                )

    def on_resize(self) -> None:
        """Keep the active table cell visible after the layout settles."""
        for table in self.query(DataTable):
            self.call_after_refresh(table.move_cursor)

    def action_close(self) -> None:
        """Dismiss the modal screen."""
        self._read_closed = True
        self.workers.cancel_node(self)
        self.dismiss()

    def check_consume_key(self, key: str, character: str | None) -> bool:
        """Keep modal close from reaching the application's rewind binding."""
        return key == "escape" or super().check_consume_key(key, character)
