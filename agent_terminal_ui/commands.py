#!/usr/bin/python
"""Command processor for the terminal UI.

This module defines the slash command registry and execution logic for the
terminal UI. It allows users to perform administrative tasks like clearing logs,
browsing history, and managing MCP tools directly from the command line.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from agent_terminal_ui.tui.exit_confirm_screen import ExitConfirmScreen

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
            "quit": self.cmd_exit,  # Alias for exit
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
            "model": self.cmd_model,
            "theme": self.cmd_theme,
            "queue": self.cmd_queue,
            "queue:clear": self.cmd_queue_clear,
            "queue:toggle": self.cmd_queue_toggle,
            "compact": self.cmd_compact,
            "branch": self.cmd_branch,
            "fork": self.cmd_branch,  # Alias
            "context": self.cmd_context,
            "diff": self.cmd_diff,
            "copy": self.cmd_copy,
            "recap": self.cmd_recap,
            "undo": self.cmd_undo,
            "rewind": self.cmd_undo,  # Alias
            "export": self.cmd_export,
            "focus": self.cmd_focus,
            "fast": self.cmd_fast,
            "permissions": self.cmd_permissions,
            "effort": self.cmd_effort,
            "color": self.cmd_color,
            "keybindings": self.cmd_keybindings,
            "memory": self.cmd_memory,
            "hooks": self.cmd_hooks,
            "agents": self.cmd_agents,
            "simplify": self.cmd_simplify,
            "loop": self.cmd_loop,
            "proactive": self.cmd_loop,  # Alias
            "add-dir": self.cmd_add_dir,
            "btw": self.cmd_btw,
        }
        # Define canonical command names (aliases map to these)
        self.canonical_commands: dict[str, str] = {
            "quit": "exit",
            "cost": "stats",
        }

    async def process(self, text: str) -> bool:
        """Process a potential command string.

        Args:
            text: The raw input string from the user.

        Returns:
            True if the input was processed as a command, False otherwise.

        """
        # Handle plain "exit" and "quit" without slash
        if text.lower().strip() in ("exit", "quit"):
            await self.commands["exit"]("")
            return True

        if not text.startswith("/"):
            return False

        parts = text[1:].split(maxsplit=1)
        if not parts or not parts[0]:
            self.app.notify("Unknown command: /", severity="warning")
            return True

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
        """Exit the terminal application (also accepts 'quit' as alias)."""

        # Show exit confirmation dialog
        def on_confirm(result: bool) -> None:
            """Handle the user's confirmation choice."""
            if result:
                try:
                    self.app.exit()
                except Exception as e:
                    # Log error but don't crash
                    import logging

                    logging.getLogger(__name__).error(f"Error during exit: {e}")

        self.app.push_screen(ExitConfirmScreen(callback=on_confirm))

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

    async def cmd_model(self, args: str) -> None:
        """Switch to a different model.

        Usage: /model <model_name> or /model to list available models.
        """
        if not args:
            # List current model and show how to switch
            current = getattr(self.app, "_current_model", "default")
            help_text = (
                f"[bold blue]Model Configuration:[/bold blue]\n"
                f"- Current model: {current or 'default (backend configured)'}\n"
                f"\n"
                f"[bold]Usage:[/bold] /model <model_name>\n"
                f"[dim]Example: /model gpt-4[/dim]\n"
                f"[dim]Example: /model claude-3-opus[/dim]\n"
            )
            self.app.query_one("#event-log").write(help_text)
            return

        # Set the new model
        self.app._current_model = args.strip()
        self.app.notify(
            f"Switched to model: {self.app._current_model}", severity="information"
        )
        self.app.query_one("#event-log").write(
            f"[dim]Switched to model: {self.app._current_model}[/dim]"
        )

    async def _submit_prompt(self, prompt: str) -> None:
        """Helper to submit a prompt to the agent."""

        # Manually trigger the text area submission logic
        class MockSubmitEvent:
            def __init__(self, value: str):
                self.value = value

        await self.app.on_input_text_area_submitted(MockSubmitEvent(prompt))

    async def register_skill_commands(self) -> None:
        """Dynamically register available skills from the backend as slash commands."""
        try:
            skills = await self.app._client.list_skills()
            logger.info(f"Retrieved {len(skills)} skills from backend")

            for skill in skills:
                skill_id = skill.get("id", skill.get("name", ""))
                if not skill_id or skill_id in self.commands:
                    continue  # Skip if no ID or already registered

                # Create a closure to capture the skill
                async def skill_handler(args: str, s=skill):
                    await self._invoke_skill(s, args)

                # Set the docstring to the skill description
                skill_description = skill.get("description", "")
                if skill_description:
                    skill_handler.__doc__ = skill_description

                self.commands[skill_id] = skill_handler
                logger.info(f"Registered skill command: {skill_id}")

            if skills:
                self.app.query_one("#event-log").write(
                    f"[dim]Registered {len(skills)} skills as slash commands.[/dim]"
                )
            else:
                self.app.query_one("#event-log").write(
                    "[yellow]No skills found on backend.[/yellow]"
                )
        except Exception as e:
            logger.error(f"Failed to register skill commands: {e}")
            try:
                self.app.query_one("#event-log").write(
                    f"[red]Failed to load skills: {e}[/red]"
                )
            except Exception:
                pass

    async def _invoke_skill(self, skill: dict[str, Any], args: str) -> None:
        """Invoke a skill by submitting a prompt to use it.

        Args:
            skill: The skill metadata dictionary.
            args: Additional arguments to pass to the skill.
        """
        skill_name = skill.get("name", skill.get("id", "unknown"))
        skill_desc = skill.get("description", "")

        # Build a prompt to use the skill
        if args:
            prompt = f"Use skill {skill_name}: {args}"
        else:
            prompt = f"Use skill {skill_name}"

        if skill_desc:
            prompt += f"\n\nSkill description: {skill_desc}"

        await self._submit_prompt(prompt)

    async def cmd_theme(self, args: str) -> None:
        """Switch between UI themes.

        Usage: /theme [theme_name] or /theme to list available themes.
        """
        from agent_terminal_ui.tui.theme import list_themes

        if not args:
            # List available themes
            available = list_themes()
            current = getattr(self.app, "_current_theme", None)
            current_name = current.name if current else "unknown"

            help_text = (
                f"[bold blue]Theme System:[/bold blue]\n"
                f"- Current theme: {current_name}\n"
                f"\n"
                f"[bold]Available themes:[/bold]\n"
            )
            for theme in available:
                marker = "👉 " if theme == current_name else "   "
                help_text += f"{marker}[cyan]{theme}[/cyan]\n"

            help_text += (
                "\n[bold]Usage:[/bold] /theme <theme_name>\n"
                "[dim]Example: /theme dracula[/dim]\n"
                "[dim]Example: /theme tokyo_night[/dim]\n"
            )

            self.app.query_one("#event-log").write(help_text)
            return

        # Switch to the specified theme
        theme_name = args.strip().lower()
        self.app.switch_theme(theme_name)

    async def cmd_queue(self, args: str) -> None:
        """Show the current message queue status. Usage: /queue"""
        queue = getattr(self.app, "_user_message_queue", [])
        queue_enabled = getattr(self.app, "_queue_enabled", True)

        if not queue:
            self.app.query_one("#event-log").write(
                "[bold blue]Message Queue:[/bold blue]\n[dim]No messages queued[/dim]"
            )
            return

        status_text = f"[bold blue]Message Queue ({len(queue)} pending):[/bold blue]\n"
        status_text += f"[dim]Queue enabled: {queue_enabled}[/dim]\n\n"

        for i, item in enumerate(queue, 1):
            message = item["message"]
            truncated = message if len(message) <= 80 else message[:77] + "..."
            status_text += f"[cyan]{i}.[/cyan] {truncated}\n"

        status_text += (
            "\n[dim]Commands:[/dim]\n"
            "[dim]/queue:clear - Clear all queued messages[/dim]\n"
            "[dim]/queue:toggle - Enable/disable queueing[/dim]\n"
        )

        self.app.query_one("#event-log").write(status_text)

    async def cmd_queue_clear(self, args: str) -> None:
        """Clear all queued messages. Usage: /queue:clear"""
        queue = getattr(self.app, "_user_message_queue", [])
        if queue:
            count = len(queue)
            self.app._user_message_queue.clear()
            self.app.query_one("#event-log").write(
                f"[bold yellow]Cleared {count} queued message(s)[/bold yellow]"
            )
        else:
            self.app.query_one("#event-log").write(
                "[dim]No queued messages to clear[/dim]"
            )

    async def cmd_queue_toggle(self, args: str) -> None:
        """Toggle message queueing on/off. Usage: /queue:toggle"""
        self.app._queue_enabled = not self.app._queue_enabled
        status = "enabled" if self.app._queue_enabled else "disabled"
        self.app.query_one("#event-log").write(
            f"[bold green]Message queueing {status}[/bold green]"
        )

    async def cmd_compact(self, args: str) -> None:
        """Compact conversation context to save tokens."""
        await self._submit_prompt(f"Compact the conversation context. {args}")

    async def cmd_branch(self, args: str) -> None:
        """Branch or fork the current conversation. Usage: /branch [name]"""
        self.app.notify(
            "Conversation branching not yet implemented", severity="warning"
        )

    async def cmd_context(self, args: str) -> None:
        """Visualize the current conversation context and token usage."""
        await self.cmd_stats(args)

    async def cmd_diff(self, args: str) -> None:
        """Show an interactive diff viewer for recent changes."""
        await self._submit_prompt("Show a diff of recent changes.")

    async def cmd_copy(self, args: str) -> None:
        """Copy the last agent response to the clipboard. Usage: /copy [N]"""
        self.app.notify(
            "Copy to clipboard from slash command not yet implemented",
            severity="warning",
        )

    async def cmd_recap(self, args: str) -> None:
        """Summarize the session context."""
        await self._submit_prompt("Summarize our session so far.")

    async def cmd_undo(self, args: str) -> None:
        """Rewind the conversation to a previous state."""
        self.app.notify("Undo/Rewind not yet implemented", severity="warning")

    async def cmd_export(self, args: str) -> None:
        """Export the current conversation history. Usage: /export [filename]"""
        if not self.app.current_session_id:
            self.app.notify("No active session to export", severity="warning")
            return

        filename = args.strip() or f"session_{self.app.current_session_id[:8]}.md"
        if not filename.endswith(".md"):
            filename += ".md"

        try:
            self.app.notify(
                f"Exporting session {self.app.current_session_id}...",
                severity="information",
            )
            chat_data = await self.app.agent_client.get_chat(
                self.app.current_session_id
            )

            if not chat_data or "messages" not in chat_data:
                self.app.notify(
                    "Failed to retrieve chat history from backend", severity="error"
                )
                return

            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# Agent Session Export: {self.app.current_session_id}\n\n")
                for msg in chat_data["messages"]:
                    role = msg.get("role", "unknown").upper()
                    content = msg.get("content", "")
                    f.write(f"### {role}\n{content}\n\n---\n\n")

            self.app.notify(f"Session exported to {filename}", severity="information")
        except Exception as e:
            self.app.notify(f"Export failed: {e}", severity="error")

    async def cmd_focus(self) -> None:
        """Toggle focus view (fullscreen mode)."""
        self.app.action_toggle_sidebar()

    async def cmd_fast(self, args: str) -> None:
        """Toggle fast mode (Haiku/Flash models). Usage: /fast [on|off]"""
        self.app.action_toggle_fast_mode()

    async def cmd_permissions(self, args: str) -> None:
        """View or update agent tool permissions."""
        self.app.notify("Permission management not yet implemented", severity="warning")

    async def cmd_effort(self, args: str) -> None:
        """Set the reasoning effort level (low/medium/high/max)."""
        self.app.notify("Effort level control not yet implemented", severity="warning")

    async def cmd_color(self, args: str) -> None:
        """Set the TUI accent color. Usage: /color [color]"""
        self.app.notify(
            "Dynamic color customization not yet implemented", severity="warning"
        )

    async def cmd_keybindings(self, args: str) -> None:
        """View or customize keyboard shortcuts."""
        self.app.action_show_help()

    async def cmd_memory(self, args: str) -> None:
        """Manage project memory (AGENTS.md). Usage: /memory [view|edit|sync]"""
        if not args or args == "view":
            await self._submit_prompt(
                "Show the contents of AGENTS.md and summarize project rules."
            )
        else:
            await self._submit_prompt(f"Manage project memory: {args}")

    async def cmd_hooks(self, args: str) -> None:
        """Manage lifecycle hooks for the agent."""
        self.app.notify("Lifecycle hooks not yet implemented", severity="warning")

    async def cmd_agents(self, args: str) -> None:
        """Manage multi-agent configurations."""
        await self._submit_prompt(
            "List available specialized agents and their configurations."
        )

    async def cmd_simplify(self, args: str) -> None:
        """Analyze code and propose simplifications."""
        await self._submit_prompt(
            f"Analyze the following code/directory and suggest simplifications: {args}"
        )

    async def cmd_loop(self, args: str) -> None:
        """Setup a recurring task. Usage: /loop [interval] [prompt]"""
        self.app.notify("Recurring tasks not yet implemented", severity="warning")

    async def cmd_add_dir(self, args: str) -> None:
        """Add a directory to the agent's working context. Usage: /add-dir <path>"""
        await self._submit_prompt(f"Add this directory to your working context: {args}")

    async def cmd_btw(self, args: str) -> None:
        """Ask a side question without adding it to the main conversation history."""
        # This would require a special API call that doesn't persist to history
        self.app.notify("Side-questions (/btw) not yet implemented", severity="warning")
