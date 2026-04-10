from collections.abc import Awaitable, Callable
import logging
from typing import Any

logger = logging.getLogger(__name__)


class CommandProcessor:
    """Registry and processor for slash commands."""

    def __init__(self, app: Any):
        self.app = app
        self.commands: dict[str, Callable[..., Awaitable[None]]] = {
            "help": self.cmd_help,
            "clear": self.cmd_clear,
            "exit": self.cmd_exit,
            "quit": self.cmd_exit,
            "mcp": self.cmd_mcp,
            "history": self.cmd_history,
        }

    async def process(self, text: str) -> bool:
        """
        Process a potential command string.
        Returns True if it was a command, False otherwise.
        """
        if not text.startswith("/"):
            return False

        parts = text[1:].split(maxsplit=1)
        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd_name in self.commands:
            try:
                await self.commands[cmd_name](args)
            except Exception as e:
                self.app.notify(
                    f"Error executing command /{cmd_name}: {e}", severity="error"
                )
            return True
        else:
            self.app.notify(f"Unknown command: /{cmd_name}", severity="warning")
            return True

    async def cmd_help(self, args: str):
        """Show available commands."""
        help_text = "[bold blue]Available Commands:[/bold blue]\n"
        for cmd in sorted(self.commands.keys()):
            doc = self.commands[cmd].__doc__ or "No description"
            help_text += f"- [bold]/{cmd}[/bold]: {doc}\n"

        self.app.query_one("#event-log").write(help_text)

    async def cmd_clear(self, args: str):
        """Clear the event log."""
        self.app.query_one("#event-log").clear()

    async def cmd_exit(self, args: str):
        """Exit the application."""
        self.app.exit()

    async def cmd_mcp(self, args: str):
        """Browse connected MCP servers and tools."""
        config = await self.app._client.get_mcp_config()
        tools = await self.app._client.list_mcp_tools()

        from agent_tui.tui.mcp_screen import MCPScreen

        self.app.push_screen(MCPScreen(config, tools))

    async def cmd_history(self, args: str):
        """Browse and select from past chat sessions."""
        chats = await self.app._client.list_chats()

        from agent_tui.tui.history_screen import HistoryScreen

        self.app.push_screen(HistoryScreen(chats), self.app._resume_session)
