#!/usr/bin/python
"""Command processor for the terminal UI.

This module defines the slash command registry and execution logic for the
terminal UI. It allows users to perform administrative tasks like clearing logs,
browsing history, and managing MCP tools directly from the command line.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


class CommandProcessor:
    """Registry and processor for terminal slash commands.

    Maps slash command strings (e.g., /help, /clear) to their respective
    asynchronous implementation methods.
    """

    def __init__(self, app: Any) -> None:
        """Initialize the command processor with a reference to the main app.

        Args:
            app: The main AgentApp instance.

        """
        self.app = app
        self.commands: dict[str, Callable[..., Awaitable[None]]] = {
            "help": self.cmd_help,
            "clear": self.cmd_clear,
            "exit": self.cmd_exit,
            "quit": self.cmd_exit,
            "mcp": self.cmd_mcp,
            "history": self.cmd_history,
            "image": self.cmd_image,
            "plan": self.cmd_plan,
            "chat": self.cmd_chat,
            "build": self.cmd_build,
            "init": self.cmd_init,
            "review": self.cmd_review,
            "test": self.cmd_test,
            "search": self.cmd_search,
            "stats": self.cmd_stats,
            "cost": self.cmd_stats,
        }

    async def process(self, text: str) -> bool:
        """Process a potential command string.

        Args:
            text: The raw input string from the user.

        Returns:
            True if the input was processed as a command, False otherwise.

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

    async def cmd_help(self, args: str) -> None:
        """Show available commands and their descriptions."""
        help_text = "[bold blue]Available Commands:[/bold blue]\n"
        for cmd in sorted(self.commands.keys()):
            doc = self.commands[cmd].__doc__ or "No description"
            help_text += f"- [bold]/{cmd}[/bold]: {doc}\n"

        self.app.query_one("#event-log").write(help_text)

    async def cmd_clear(self, args: str) -> None:
        """Clear the current event log."""
        self.app.query_one("#event-log").clear()

    async def cmd_exit(self, args: str) -> None:
        """Exit the terminal application."""
        self.app.exit()

    async def cmd_mcp(self, args: str) -> None:
        """Browse connected MCP servers and their available tools."""
        config = await self.app._client.get_mcp_config()
        tools = await self.app._client.list_mcp_tools()

        # Fixed legacy import from agent_tui to agent_terminal_ui
        from agent_terminal_ui.tui.mcp_screen import MCPScreen

        self.app.push_screen(MCPScreen(config, tools))

    async def cmd_history(self, args: str) -> None:
        """Browse and select from historical chat sessions."""
        chats = await self.app._client.list_chats()

        # Fixed legacy import from agent_tui to agent_terminal_ui
        from agent_terminal_ui.tui.history_screen import HistoryScreen

        self.app.push_screen(HistoryScreen(chats), self.app._resume_session)

    async def cmd_image(self, args: str) -> None:
        """Attach an image file to the next agent prompt.

        Usage: /image path/to/image.png
        """
        import base64
        from pathlib import Path

        path_str = args.strip().strip('"').strip("'")
        path = Path(path_str)
        if not path.exists():
            self.app.notify(f"Image file not found: {path}", severity="error")
            return

        try:
            raw_bytes = path.read_bytes()
            suffix = path.suffix.lower().strip(".")
            if suffix in ["jpg", "jpeg"]:
                media_type = "image/jpeg"
            elif suffix == "png":
                media_type = "image/png"
            elif suffix == "gif":
                media_type = "image/gif"
            elif suffix == "webp":
                media_type = "image/webp"
            else:
                media_type = f"image/{suffix}"

            # Store in app state for next submission
            if not hasattr(self.app, "_pending_parts"):
                self.app._pending_parts = []

            img_b64 = base64.b64encode(raw_bytes).decode()
            self.app._pending_parts.append({"image": img_b64, "media_type": media_type})

            self.app.notify(f"Attached image: {path.name}", severity="information")
            self.app.query_one("#event-log").write(
                f"[dim]Attached image: {path.name}[/dim]"
            )
        except Exception as e:
            self.app.notify(f"Failed to load image: {e}", severity="error")

    async def cmd_plan(self, args: str) -> None:
        """Switch agent to planning mode. Usage: /plan [optional prompt]"""
        await self._switch_mode("plan", args)

    async def cmd_chat(self, args: str) -> None:
        """Switch agent to chat (ask) mode. Usage: /chat [optional prompt]"""
        await self._switch_mode("ask", args)

    async def cmd_build(self, args: str) -> None:
        """Switch agent to build/code mode. Usage: /build [optional prompt]"""
        await self._switch_mode("code", args)

    async def _switch_mode(self, new_mode: str, args: str) -> None:
        """Helper to switch mode, update UI, and optionally submit a prompt."""
        self.app._agent_mode = new_mode
        # The mode visually might be labelled differently
        display_mode = new_mode if new_mode != "ask" else "chat"

        # update status line
        from agent_terminal_ui.tui.status_line import StatusLine

        self.app.query_one(StatusLine).set_mode(display_mode)
        self.app.notify(f"Switched to [{display_mode}] mode", severity="information")
        self.app.query_one("#event-log").write(
            f"[dim]Switched to {display_mode} mode.[/dim]"
        )

        if args:
            # Manually trigger the text area submission logic
            class MockSubmitEvent:
                def __init__(self, value: str):
                    self.value = value

            await self.app.on_input_text_area_submitted(MockSubmitEvent(args))

    async def cmd_init(self, args: str) -> None:
        """Initialize the project using Spec-Driven Development (SDD)."""
        await self._submit_prompt("Initialize the project structure using setup_sdd.")

    async def cmd_review(self, args: str) -> None:
        """Perform a code review of the current workspace."""
        await self._submit_prompt(f"Perform a comprehensive code review. {args}")

    async def cmd_test(self, args: str) -> None:
        """Run tests and report results."""
        await self._submit_prompt(
            f"Run tests for this project and report the outcome. {args}"
        )

    async def cmd_search(self, args: str) -> None:
        """Search the codebase for a pattern. Usage: /search <query>"""
        if not args:
            self.app.notify("Usage: /search <query>", severity="warning")
            return
        await self._submit_prompt(f"Search the codebase for: {args}")

    async def cmd_stats(self, args: str) -> None:
        """Show usage statistics and cost for the current session."""
        # In a real app, this would fetch data from the server
        # For now, we use a placeholder or check app state if available
        usage = getattr(self.app, "_last_usage", None)
        if usage:
            stats = (
                f"[bold blue]Session Statistics:[/bold blue]\n"
                f"- Total Tokens: {usage.get('total_tokens', 0)}\n"
                f"- Estimated Cost: ${usage.get('estimated_cost_usd', 0):.4f}\n"
            )
        else:
            stats = (
                "[yellow]Usage statistics not yet available for this session.[/yellow]"
            )

        self.app.query_one("#event-log").write(stats)

    async def _submit_prompt(self, prompt: str) -> None:
        """Helper to submit a prompt to the agent."""

        # Manually trigger the text area submission logic
        class MockSubmitEvent:
            def __init__(self, value: str):
                self.value = value

        await self.app.on_input_text_area_submitted(MockSubmitEvent(prompt))
