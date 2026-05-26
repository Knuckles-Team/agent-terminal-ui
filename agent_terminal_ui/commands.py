#!/usr/bin/python
"""Command processor for the terminal UI.

This module defines the slash command registry and execution logic for the
terminal UI. It allows users to perform administrative tasks like clearing logs,
browsing history, and managing MCP tools directly from the command line.
"""

import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

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
        self._log_widget = None  # cached reference
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
            "context": self.cmd_context,
            "diff": self.cmd_diff,
            "recap": self.cmd_recap,
            "export": self.cmd_export,
            "focus": self.cmd_focus,
            "fast": self.cmd_fast,
            "keybindings": self.cmd_keybindings,
            "memory": self.cmd_memory,
            "agents": self.cmd_agents,
            "simplify": self.cmd_simplify,
            "add-dir": self.cmd_add_dir,
            "graph": self.cmd_graph,
            "kb": self.cmd_kb,
            "sdd": self.cmd_sdd,
            "impact": self.cmd_impact,
            "mcp:reload": self.cmd_mcp_reload,
            "codemap": self.cmd_codemap,
            "resources": self.cmd_resources,
            "pipeline": self.cmd_pipeline,
            "maintenance": self.cmd_maintenance,
            "cron": self.cmd_cron,
            "config": self.cmd_config,
            "logs": self.cmd_logs,
            "prompts": self.cmd_prompts,
            "skills": self.cmd_skills_only,
            "tools": self.cmd_tools_only,
            # --- Agent View & Goal commands (TUI-20, ORCH-5.0) ---
            "goal": self.cmd_goal,
            "goal:status": self.cmd_goal_status,
            "goal:cancel": self.cmd_goal_cancel,
            "goal:history": self.cmd_goal_history,
            "bg": self.cmd_bg,
            "attach": self.cmd_attach,
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
            # Try to query the gateway commands/execute endpoint
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.app.agent_client.base_url}/api/enhanced/commands/execute",
                        json={"command": text},
                        timeout=15.0,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        response_markdown = data.get("response_markdown", "")
                        client_actions = data.get("client_actions", [])

                        try:
                            conv = self.app.query_one("Conversation")
                            await conv.add_agent_response(response_markdown)
                        except Exception:
                            self.app.notify(
                                response_markdown[:100], severity="information"
                            )

                        # Handle client actions
                        for action_dict in client_actions:
                            action = action_dict.get("action")
                            if action == "clear_chat":
                                with contextlib.suppress(Exception):
                                    conv = self.app.query_one("Conversation")
                                    await conv.clear_conversation()
                                    await conv.add_info(
                                        "🧹 Chat log cleared via slash command."
                                    )
                        return True
                    else:
                        self.app.notify(
                            f"Gateway command failed: Code {response.status_code}",
                            severity="error",
                        )
                        return True
            except Exception as e:
                self.app.notify(
                    f"Unknown command: /{cmd_name} (Gateway offline: {e})",
                    severity="warning",
                )
                return True

    async def cmd_help(self, args: str) -> None:
        """Show available commands and their descriptions."""
        help_text = "[bold blue]Available Commands:[/bold blue]\n"
        for cmd in sorted(self.commands.keys()):
            doc = self.commands[cmd].__doc__ or "No description"
            help_text += f"- [bold]/{cmd}[/bold]: {doc}\n"

        await self.app.query_one("Conversation").add_info(help_text)

    async def cmd_clear(self, args: str) -> None:
        """Clear the current event log."""
        await self.app.query_one("Conversation").clear_conversation()

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
            await self.app.query_one("Conversation").add_info(
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
        await self.app.query_one("Conversation").add_info(
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

        await self.app.query_one("Conversation").add_info(stats)

    async def cmd_model(self, args: str) -> None:
        """List, select, or inspect configured models.

        Usage:
            /model                 alias for /model list
            /model list            show all configured models in a table
            /model show            show the currently active model
            /model set <id>        select a model id for subsequent turns
            /model <id>            legacy shorthand for /model set <id>
        """
        tokens = args.strip().split(maxsplit=1)
        subcommand = tokens[0].lower() if tokens else "list"
        value = tokens[1].strip() if len(tokens) > 1 else ""

        if subcommand in ("", "list"):
            await self._model_list()
        elif subcommand == "show":
            await self._model_show()
        elif subcommand == "set":
            await self._model_set(value)
        else:
            # Legacy shorthand: ``/model <id>`` -> ``/model set <id>``.
            # Combine tokens back into the original free-form id so multi-
            # word ids (``/model my cool model``) still work.
            shorthand = args.strip()
            await self._model_set_shorthand(shorthand)

    async def _model_set_shorthand(self, model_id: str) -> None:
        """Legacy bare ``/model <id>`` that tolerates unknown ids.

        Unlike ``/model set <id>``, this shorthand accepts ids that are
        not present in the backend registry (so existing workflows that
        pass raw provider model strings keep working). When the id *is*
        in the registry, the richer ``_model_set`` flow is used so users
        get the same validation message.
        """
        registry = await self.app._client.list_configured_models()
        models = registry.get("models") or []
        match = next((m for m in models if m.get("id") == model_id), None)
        if match is not None:
            await self._model_set(model_id)
            return

        self.app._current_model_id = model_id
        self.app._current_model = model_id
        self.app.notify(f"Switched to model: {model_id}", severity="information")
        await self.app.query_one("Conversation").add_info(
            f"[dim]Switched to model: {model_id}[/dim]"
        )

    async def _model_list(self) -> None:
        """Render the configured model registry as a Rich table."""
        registry = await self.app._client.list_configured_models()
        models = registry.get("models") or []
        default_id = registry.get("default_id")
        active_id = (
            getattr(self.app, "_current_model_id", None)
            or getattr(self.app, "_current_model", None)
            or default_id
        )

        if not models:
            await self.app.query_one("Conversation").add_info(
                "[yellow]No models configured on the backend. "
                "Set MODELS_CONFIG or configure single-model kwargs.[/yellow]"
            )
            return

        table = Table(title="Configured Models", show_lines=False)
        table.add_column("Active", justify="center", style="cyan", width=6)
        table.add_column("ID", style="bold")
        table.add_column("Name")
        table.add_column("Provider")
        table.add_column("Tier")
        table.add_column("Tags")
        table.add_column("Default", justify="center", width=7)
        table.add_column("Cost / 1M (in / out)")

        for m in models:
            cost = m.get("cost") or {}
            cost_in = float(cost.get("input", 0.0))
            cost_out = float(cost.get("output", 0.0))
            cost_str = f"${cost_in:.2f} / ${cost_out:.2f}"
            tags = ", ".join(m.get("tags") or []) or "-"
            is_active = m.get("id") == active_id
            is_default = bool(m.get("is_default"))
            table.add_row(
                "*" if is_active else "",
                str(m.get("id", "")),
                str(m.get("name", "")),
                str(m.get("provider", "")),
                str(m.get("tier", "")),
                tags,
                "yes" if is_default else "",
                cost_str,
            )

        event_log = self.app.query_one("Conversation")
        await event_log.add_info(table)
        await event_log.add_info(
            "[dim]Use `/model set <id>` to switch, `/model show` to inspect.[/dim]"
        )

    async def _model_show(self) -> None:
        """Display the currently active model, resolving the backend default."""
        registry = await self.app._client.list_configured_models()
        models = registry.get("models") or []
        default_id = registry.get("default_id")
        active_id = (
            getattr(self.app, "_current_model_id", None)
            or getattr(self.app, "_current_model", None)
            or default_id
        )
        match = next((m for m in models if m.get("id") == active_id), None)

        if match is None:
            await self.app.query_one("Conversation").add_info(
                "[yellow]No active model. "
                "Run `/model list` to see what is configured.[/yellow]"
            )
            return

        cost = match.get("cost") or {}
        cost_in = float(cost.get("input", 0.0))
        cost_out = float(cost.get("output", 0.0))
        panel = Panel(
            (
                f"[bold]ID:[/bold] {match.get('id')}\n"
                f"[bold]Name:[/bold] {match.get('name')}\n"
                f"[bold]Provider:[/bold] {match.get('provider')}\n"
                f"[bold]Model ID:[/bold] {match.get('model_id')}\n"
                f"[bold]Tier:[/bold] {match.get('tier')}\n"
                f"[bold]Tags:[/bold] {', '.join(match.get('tags') or []) or '-'}\n"
                f"[bold]Cost / 1M (in / out):[/bold] "
                f"${cost_in:.2f} / ${cost_out:.2f}\n"
                f"[bold]Default:[/bold] "
                f"{'yes' if match.get('is_default') else 'no'}"
            ),
            title="Active Model",
            border_style="cyan",
        )
        await self.app.query_one("Conversation").add_info(panel)

    async def _model_set(self, model_id: str) -> None:
        """Select a model id for subsequent turns."""
        model_id = model_id.strip()
        if not model_id:
            await self.app.query_one("Conversation").add_info(
                "[yellow]Usage: /model set <id>[/yellow]"
            )
            return

        registry = await self.app._client.list_configured_models()
        models = registry.get("models") or []
        match = next((m for m in models if m.get("id") == model_id), None)

        if match is None:
            available = ", ".join(m.get("id", "") for m in models) or "<none>"
            await self.app.query_one("Conversation").add_info(
                f"[red]Model id '{model_id}' not found.[/red]\n"
                f"[dim]Available: {available}[/dim]"
            )
            return

        self.app._current_model_id = model_id
        # ``_current_model`` is the attribute already wired into the client
        # stream call; keep it in sync so existing send paths pick up the
        # override without code changes elsewhere.
        self.app._current_model = model_id
        self.app.notify(f"Switched to model: {model_id}", severity="information")
        await self.app.query_one("Conversation").add_info(
            f"[green]Active model set to {model_id}[/green] "
            f"([dim]{match.get('provider')}:{match.get('model_id')}[/dim])"
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
                await self.app.query_one("Conversation").add_info(
                    f"[dim]Registered {len(skills)} skills as slash commands.[/dim]"
                )
            else:
                await self.app.query_one("Conversation").add_info(
                    "[yellow]No skills found on backend.[/yellow]"
                )
        except Exception as e:
            logger.error(f"Failed to register skill commands: {e}")
            with contextlib.suppress(Exception):
                await self.app.query_one("Conversation").add_info(
                    f"[red]Failed to load skills: {e}[/red]"
                )

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

            await self.app.query_one("Conversation").add_info(help_text)
            return

        # Switch to the specified theme
        theme_name = args.strip().lower()
        self.app.switch_theme(theme_name)

    async def cmd_queue(self, args: str) -> None:
        """Show the current message queue status. Usage: /queue"""
        queue = getattr(self.app, "_user_message_queue", [])
        queue_enabled = getattr(self.app, "_queue_enabled", True)

        if not queue:
            await self.app.query_one("Conversation").add_info(
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

        await self.app.query_one("Conversation").add_info(status_text)

    async def cmd_queue_clear(self, args: str) -> None:
        """Clear all queued messages. Usage: /queue:clear"""
        queue = getattr(self.app, "_user_message_queue", [])
        if queue:
            count = len(queue)
            self.app._user_message_queue.clear()
            await self.app.query_one("Conversation").add_info(
                f"[bold yellow]Cleared {count} queued message(s)[/bold yellow]"
            )
        else:
            await self.app.query_one("Conversation").add_info(
                "[dim]No queued messages to clear[/dim]"
            )

    async def cmd_queue_toggle(self, args: str) -> None:
        """Toggle message queueing on/off. Usage: /queue:toggle"""
        self.app._queue_enabled = not self.app._queue_enabled
        status = "enabled" if self.app._queue_enabled else "disabled"
        await self.app.query_one("Conversation").add_info(
            f"[bold green]Message queueing {status}[/bold green]"
        )

    async def cmd_compact(self, args: str) -> None:
        """Compact conversation context to save tokens."""
        await self._submit_prompt(f"Compact the conversation context. {args}")

    async def cmd_context(self, args: str) -> None:
        """Visualize the current conversation context and token usage."""
        await self.cmd_stats(args)

    async def cmd_diff(self, args: str) -> None:
        """Show an interactive diff viewer for recent changes."""
        await self._submit_prompt("Show a diff of recent changes.")

    async def cmd_recap(self, args: str) -> None:
        """Summarize the session context."""
        await self._submit_prompt("Summarize our session so far.")

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
            chat_data = await self.app._client.get_chat(self.app.current_session_id)

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

    async def cmd_keybindings(self, args: str) -> None:
        """View or customize keyboard shortcuts."""
        self.app.action_show_help()

    async def cmd_logs(self, args: str) -> None:
        """Toggle server logs visibility (Ctrl+V)."""
        self.app.action_toggle_logs()

    async def cmd_memory(self, args: str) -> None:
        """Manage knowledge-graph memory nodes.

        Usage: /memory [list | add <content> | get <id> | delete <id>
                        | search <query> | review | <prompt>]
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")

        if sub in ("", "list"):
            try:
                memories = await self.app._client.list_graph_nodes(node_type="Memory")
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "memory list", exc)
                return
            await log.add_info(self._render_memory_list(memories))
            return

        if sub == "add":
            if not rest.strip():
                self.app.notify("Usage: /memory add <content>", severity="warning")
                return
            try:
                created = await self.app._client.create_memory(
                    {"content": rest.strip()}
                )
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "memory add", exc)
                return
            mem_id = created.get("id", "<unknown>")
            self.app.notify(f"Memory created: {mem_id}", severity="information")
            await log.add_info(f"[green]Memory created:[/green] {mem_id}")
            return

        if sub == "get":
            if not rest.strip():
                self.app.notify("Usage: /memory get <id>", severity="warning")
                return
            try:
                memory = await self.app._client.get_memory(rest.strip())
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "memory get", exc)
                return
            await log.add_info(self._render_memory_detail(memory))
            return

        if sub == "delete":
            if not rest.strip():
                self.app.notify("Usage: /memory delete <id>", severity="warning")
                return
            mem_id = rest.strip()
            try:
                await self.app._client.delete_memory(mem_id)
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "memory delete", exc)
                return
            self.app.notify(f"Memory deleted: {mem_id}", severity="warning")
            await log.add_info(f"[yellow]Memory deleted:[/yellow] {mem_id}")
            return

        if sub == "search":
            if not rest.strip():
                self.app.notify("Usage: /memory search <query>", severity="warning")
                return
            try:
                hits = await self.app._client.search_graph(rest.strip())
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "memory search", exc)
                return
            await log.add_info(self._render_graph_search(rest.strip(), hits))
            return

        if sub == "review":
            await self._submit_prompt(
                "Review the current knowledge-graph memories and summarize key items."
            )
            return

        await self._submit_prompt(f"Manage project memory: {args}")

    async def cmd_agents(self, args: str) -> None:
        """Open the Agent View — multi-session dashboard (TUI-20)."""
        if hasattr(self.app, "switch_mode"):
            self.app.switch_mode("agents")
        else:
            self.app.notify(
                "Agent View requires screen modes. Use /history instead.",
                severity="warning",
            )

    async def cmd_goal(self, args: str) -> None:
        """
        Start an autonomous goal loop.
        Usage: /goal <objective> [until <end_state>] [without <constraints>]
        """
        if not args.strip():
            self.app.notify(
                "Usage: /goal <objective> until <end_state> [without <constraints>]",
                severity="warning",
            )
            return

        from agent_utilities.models.goal import GoalSpec

        spec = GoalSpec.parse_goal_input(args)
        spec.session_id = getattr(self.app, "_session_id", "")

        log = self.app.query_one("Conversation")
        await log.add_info(
            f"🎯 **Goal Started**\n"
            f"**Objective:** {spec.objective}\n"
            + (f"**Success Criteria:** {spec.end_state}\n" if spec.end_state else "")
            + (
                f"**Constraints:** {', '.join(spec.constraints)}\n"
                if spec.constraints
                else ""
            )
            + (
                f"**Validation:** `{spec.validation_cmd}`\n"
                if spec.validation_cmd
                else ""
            )
            + f"**Max Iterations:** {spec.max_iterations}\n"
            + f"**Auto-approve:** {spec.auto_approve}"
        )

        # Store the active goal on the app and submit the first prompt
        self.app._active_goal = spec
        goal_prompt = (
            spec.to_system_prompt() + f"\n\nBegin working on: {spec.objective}"
        )
        await self._submit_prompt(goal_prompt)

    async def cmd_goal_status(self, args: str) -> None:
        """Show the status of the current goal."""
        goal = getattr(self.app, "_active_goal", None)
        if goal is None:
            self.app.notify("No active goal.", severity="information")
            return

        log = self.app.query_one("Conversation")
        iteration = getattr(self.app, "_goal_iteration", 0)
        await log.add_info(
            f"🎯 **Goal Status**\n"
            f"**Objective:** {goal.objective}\n"
            f"**Iteration:** {iteration}/{goal.max_iterations}\n"
            f"**Session:** {goal.session_id}"
        )

    async def cmd_goal_cancel(self, args: str) -> None:
        """Cancel the current goal."""
        goal = getattr(self.app, "_active_goal", None)
        if goal is None:
            self.app.notify("No active goal to cancel.", severity="information")
            return

        self.app._active_goal = None
        self.app._goal_iteration = 0
        log = self.app.query_one("Conversation")
        await log.add_info("🚫 **Goal Cancelled**")
        self.app.notify("Goal cancelled.", severity="information")

    async def cmd_goal_history(self, args: str) -> None:
        """Show history of completed goals."""
        log = self.app.query_one("Conversation")
        await log.add_info(
            "📋 **Goal History**\n"
            "Goal history is stored in the Knowledge Graph as GoalNode entities.\n"
            "Use `/graph search goal` to browse past goals."
        )

    async def cmd_bg(self, args: str) -> None:
        """Background the current session. The agent continues working autonomously."""
        log = self.app.query_one("Conversation")
        session_id = getattr(self.app, "_session_id", "")
        if not session_id:
            self.app.notify("No active session to background.", severity="warning")
            return

        # Mark session as backgrounded in session manager
        if hasattr(self.app, "_session_manager") and self.app._session_manager:
            conn = self.app._session_manager._get_conn()
            with contextlib.suppress(Exception):
                conn.execute(
                    "UPDATE sessions SET background = 1 WHERE id = ?",
                    (session_id,),
                )
                conn.commit()

        await log.add_info(
            "⬇️ **Session Backgrounded**\n"
            "This session will continue running autonomously.\n"
            "Use `/agents` or press `←` to view all sessions."
        )
        self.app.notify(
            f"Session {session_id[:8]} backgrounded.", severity="information"
        )

        # Switch to agent view if available
        if hasattr(self.app, "switch_mode"):
            self.app.switch_mode("agents")

    async def cmd_attach(self, args: str) -> None:
        """Attach to a specific session. Usage: /attach <session_id>"""
        session_id = args.strip()
        if not session_id:
            self.app.notify(
                "Usage: /attach <session_id>",
                severity="warning",
            )
            return
        self.app.notify(
            f"Attaching to session {session_id[:8]}...",
            severity="information",
        )
        # Switch to the specified session
        if hasattr(self.app, "_switch_session"):
            await self.app._switch_session(session_id)

    async def cmd_simplify(self, args: str) -> None:
        """Analyze code and propose simplifications."""
        await self._submit_prompt(
            f"Analyze the following code/directory and suggest simplifications: {args}"
        )

    async def cmd_add_dir(self, args: str) -> None:
        """Add a directory to the agent's working context. Usage: /add-dir <path>"""
        await self._submit_prompt(f"Add this directory to your working context: {args}")

    async def cmd_graph(self, args: str) -> None:
        """Explore the knowledge graph.

        Usage: /graph [stats | nodes [type] | search <query> | impact <symbol>]
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")

        if sub in ("", "stats"):
            try:
                stats = await self.app._client.get_graph_stats()
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "graph stats", exc)
                return
            await log.add_info(self._render_graph_stats(stats))
            return

        if sub == "nodes":
            node_type = rest.strip() or None
            try:
                nodes = await self.app._client.list_graph_nodes(node_type=node_type)
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "graph nodes", exc)
                return
            await log.add_info(self._render_graph_nodes(nodes, node_type))
            return

        if sub == "search":
            if not rest.strip():
                self.app.notify("Usage: /graph search <query>", severity="warning")
                return
            try:
                hits = await self.app._client.search_graph(rest.strip())
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "graph search", exc)
                return
            await log.add_info(self._render_graph_search(rest.strip(), hits))
            return

        if sub == "impact":
            if not rest.strip():
                self.app.notify("Usage: /graph impact <symbol>", severity="warning")
                return
            symbol = rest.strip()
            try:
                impacts = await self.app._client.get_graph_impact(symbol)
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "graph impact", exc)
                return
            await log.add_info(self._render_graph_impact(symbol, impacts))
            return

        self.app.notify(f"Unknown /graph subcommand: {sub}", severity="warning")

    async def cmd_kb(self, args: str) -> None:
        """Browse and ingest knowledge bases.

        Usage: /kb [list | search <query> [--kb <id>]
                    | article <id> | ingest <source> <kb_name>]
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")

        if sub in ("", "list"):
            try:
                kbs = await self.app._client.list_kbs()
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "kb list", exc)
                return
            await log.add_info(self._render_kb_list(kbs))
            return

        if sub == "search":
            usage = "Usage: /kb search <query> [--kb <id>]"
            if not rest.strip():
                self.app.notify(usage, severity="warning")
                return
            query, kb_id = self._split_kb_flag(rest)
            if not query:
                self.app.notify(usage, severity="warning")
                return
            try:
                hits = await self.app._client.search_kb(query, kb_id=kb_id)
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "kb search", exc)
                return
            await log.add_info(self._render_kb_search(query, hits, kb_id))
            return

        if sub == "article":
            if not rest.strip():
                self.app.notify("Usage: /kb article <article_id>", severity="warning")
                return
            article_id = rest.strip()
            try:
                article = await self.app._client.get_kb_article(article_id)
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "kb article", exc)
                return
            await log.add_info(self._render_kb_article(article))
            return

        if sub == "ingest":
            parts = rest.split(maxsplit=1)
            if len(parts) < 2:
                self.app.notify(
                    "Usage: /kb ingest <source> <kb_name>", severity="warning"
                )
                return
            source, kb_name = parts[0], parts[1].strip()
            try:
                result = await self.app._client.ingest_kb(source, kb_name)
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "kb ingest", exc)
                return
            status = result.get("status", "ok")
            self.app.notify(
                f"Ingestion started: {kb_name} ({status})", severity="information"
            )
            await log.add_info(
                f"[green]Ingested[/green] [bold]{source}[/bold] "
                f"into [cyan]{kb_name}[/cyan] (status: {status})"
            )
            return

        self.app.notify(f"Unknown /kb subcommand: {sub}", severity="warning")

    async def cmd_sdd(self, args: str) -> None:
        """Inspect Spec-Driven Development artifacts.

        Usage: /sdd [constitution | specs | plans | tasks [plan_id]]
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")

        if sub == "constitution":
            try:
                constitution = await self.app._client.get_constitution()
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "sdd constitution", exc)
                return
            if not constitution:
                await log.add_info("[yellow]No constitution defined yet.[/yellow]")
                return
            await log.add_info(self._render_constitution(constitution))
            return

        if sub == "specs":
            try:
                specs = await self.app._client.list_specs()
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "sdd specs", exc)
                return
            await log.add_info(self._render_specs(specs))
            return

        if sub == "plans":
            try:
                plans = await self.app._client.list_plans()
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "sdd plans", exc)
                return
            await log.add_info(self._render_plans(plans))
            return

        if sub == "tasks":
            plan_id = rest.strip() or None
            try:
                tasks = await self.app._client.get_tasks(plan_id=plan_id)
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "sdd tasks", exc)
                return
            # Server may wrap tasks in {"tasks": [...]} or return a list directly.
            if isinstance(tasks, dict) and "tasks" in tasks:
                tasks = tasks["tasks"]
            await log.add_info(self._render_tasks(tasks, plan_id))
            return

        self.app.notify(
            "Usage: /sdd [constitution | specs | plans | tasks [plan_id]]",
            severity="warning",
        )

    async def cmd_impact(self, args: str) -> None:
        """Inspect topological impact for a symbol. Usage: /impact <symbol>"""
        log = self.app.query_one("Conversation")
        query = args.strip()
        if not query or query in ("-h", "--help"):
            await log.add_info(
                "[bold blue]/impact <symbol>[/bold blue]\n"
                "[dim]Example:[/dim] /impact pkg.module.func\n"
                "Shows nodes impacted by a change to <symbol>."
            )
            return
        try:
            impacts = await self.app._client.get_impact(query)
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "impact", exc)
            return
        except Exception as exc:
            await log.add_info(f"[red]Error (impact): {exc}[/red]")
            return
        await log.add_info(self._render_impact_table(query, impacts))

    async def cmd_mcp_reload(self, args: str) -> None:
        """Hot-reload the backend MCP server configuration. Usage: /mcp:reload"""
        log = self.app.query_one("Conversation")
        try:
            result = await self.app._client.reload_mcp()
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "mcp:reload", exc)
            return
        except Exception as exc:
            await log.add_info(f"[red]Error (mcp:reload): {exc}[/red]")
            return

        status = result.get("status", "unknown")
        if status == "error":
            error = result.get("error", "unknown error")
            self.app.notify(f"MCP reload failed: {error}", severity="error")
            await log.add_info(f"[red]MCP reload failed:[/red] {error}")
            return

        agent_count = result.get("agents", 0)
        tool_count = result.get("tools", 0)
        message = (
            f"MCP config reloaded. {agent_count} servers active ({tool_count} tools)."
        )
        self.app.notify(message, severity="information")
        await log.add_info(f"[green]{message}[/green]")

    async def cmd_codemap(self, args: str) -> None:
        """Generate a codebase codemap. Usage: /codemap <prompt>"""
        log = self.app.query_one("Conversation")
        prompt = args.strip()
        if not prompt:
            self.app.notify("Usage: /codemap <prompt>", severity="warning")
            return
        try:
            result = await self.app._client.generate_codemap(prompt)
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "codemap", exc)
            return
        except Exception as exc:
            await log.add_info(f"[red]Error (codemap): {exc}[/red]")
            return

        if result.get("status") == "error":
            error = result.get("message", "unknown error")
            await log.add_info(f"[red]Codemap generation failed:[/red] {error}")
            return

        artifact = result.get("artifact") or {}
        mermaid = artifact.get("mermaid")
        markdown = artifact.get("markdown")

        codemap_id = result.get("codemap_id") or artifact.get("id", "")
        header = f"[bold cyan]Codemap[/bold cyan] [dim]{codemap_id}[/dim]"
        await log.add_info(header)

        if mermaid:
            await log.add_info(Syntax(mermaid, "mermaid", word_wrap=True))
        if markdown:
            await log.add_info(Panel(markdown, title="Codemap (markdown)"))
        if not mermaid and not markdown:
            await log.add_info(
                "[yellow]Codemap returned no renderable content.[/yellow]"
            )

    async def cmd_resources(self, args: str) -> None:
        """List or spawn callable resources.

        Usage: /resources [list | spawn <json_spec>]
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")

        if sub in ("", "list"):
            try:
                resources = await self.app._client.list_resources()
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "resources list", exc)
                return
            except Exception as exc:
                await log.add_info(f"[red]Error (resources list): {exc}[/red]")
                return
            await log.add_info(self._render_resources_table(resources))
            return

        if sub == "spawn":
            if not rest.strip():
                self.app.notify(
                    "Usage: /resources spawn <json_spec>", severity="warning"
                )
                return
            try:
                spec = json.loads(rest)
            except json.JSONDecodeError as exc:
                self.app.notify(
                    f"Invalid JSON for /resources spawn: {exc}", severity="error"
                )
                await log.add_info(f"[red]Invalid JSON for spawn spec:[/red] {exc}")
                return
            if not isinstance(spec, dict):
                self.app.notify("Spawn spec must be a JSON object", severity="error")
                return
            try:
                spawned = await self.app._client.spawn_resource(spec)
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "resources spawn", exc)
                return
            except Exception as exc:
                await log.add_info(f"[red]Error (resources spawn): {exc}[/red]")
                return
            spawned_id = spawned.get("id") or spawned.get("name", "<unknown>")
            self.app.notify(f"Spawned resource: {spawned_id}", severity="information")
            await log.add_info(f"[green]Spawned resource:[/green] {spawned_id}")
            return

        self.app.notify(f"Unknown /resources subcommand: {sub}", severity="warning")

    async def cmd_pipeline(self, args: str) -> None:
        """Inspect or trigger the ingestion pipeline.

        Usage: /pipeline [status | run [phase]]
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")

        if sub in ("", "status"):
            try:
                status = await self.app._client.get_pipeline_status()
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "pipeline status", exc)
                return
            except Exception as exc:
                await log.add_info(f"[red]Error (pipeline status): {exc}[/red]")
                return
            await log.add_info(self._render_pipeline_status(status))
            return

        if sub == "run":
            phase = rest.strip() or None
            label = phase or "full pipeline"
            self.app.notify(f"Triggering pipeline: {label}", severity="information")
            try:
                result = await self.app._client.trigger_pipeline(phase)
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "pipeline run", exc)
                return
            except Exception as exc:
                await log.add_info(f"[red]Error (pipeline run): {exc}[/red]")
                return
            status_str = result.get("status", "unknown")
            await log.add_info(
                f"[green]Pipeline triggered[/green] "
                f"[bold]{label}[/bold] (status: {status_str})"
            )
            return

        self.app.notify(f"Unknown /pipeline subcommand: {sub}", severity="warning")

    async def cmd_maintenance(self, args: str) -> None:
        """Inspect or trigger graph maintenance operations.

        Usage: /maintenance [status | run [operation]]
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")

        if sub in ("", "status"):
            try:
                status = await self.app._client.get_maintenance_status()
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "maintenance status", exc)
                return
            except Exception as exc:
                await log.add_info(f"[red]Error (maintenance status): {exc}[/red]")
                return
            await log.add_info(self._render_maintenance_status(status))
            return

        if sub == "run":
            operation = rest.strip() or None
            label = operation or "full maintenance"
            self.app.notify(f"Triggering maintenance: {label}", severity="information")
            try:
                result = await self.app._client.trigger_maintenance(operation)
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "maintenance run", exc)
                return
            except Exception as exc:
                await log.add_info(f"[red]Error (maintenance run): {exc}[/red]")
                return
            status_str = result.get("status", "unknown")
            await log.add_info(
                f"[green]Maintenance triggered[/green] "
                f"[bold]{label}[/bold] (status: {status_str})"
            )
            return

        self.app.notify(f"Unknown /maintenance subcommand: {sub}", severity="warning")

    async def cmd_cron(self, args: str) -> None:
        """Inspect cron calendar and execution logs.

        Usage: /cron [calendar | logs [limit]]
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")

        if sub in ("", "calendar"):
            try:
                tasks = await self.app._client.get_cron_calendar()
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "cron calendar", exc)
                return
            except Exception as exc:
                await log.add_info(f"[red]Error (cron calendar): {exc}[/red]")
                return
            await log.add_info(self._render_cron_calendar(tasks))
            return

        if sub == "logs":
            limit = self._parse_positive_int(rest.strip(), default=20)
            try:
                logs = await self.app._client.get_cron_logs()
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "cron logs", exc)
                return
            except Exception as exc:
                await log.add_info(f"[red]Error (cron logs): {exc}[/red]")
                return
            await log.add_info(self._render_cron_logs(logs[:limit], limit))
            return

        self.app.notify(f"Unknown /cron subcommand: {sub}", severity="warning")

    async def cmd_config(self, args: str) -> None:
        """Display or update the backend configuration.

        Usage: /config [show | set <key> <value>]
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")

        if sub in ("", "show"):
            try:
                config = await self.app._client.get_backend_config()
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "config show", exc)
                return
            except Exception as exc:
                await log.add_info(f"[red]Error (config show): {exc}[/red]")
                return
            await log.add_info(self._render_backend_config(config))
            return

        if sub == "set":
            key, _, value = rest.strip().partition(" ")
            if not key or not value:
                self.app.notify("Usage: /config set <key> <value>", severity="warning")
                return
            payload = {key: value.strip()}
            try:
                result = await self.app._client.update_backend_config(payload)
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "config set", exc)
                return
            except Exception as exc:
                await log.add_info(f"[red]Error (config set): {exc}[/red]")
                return
            status = result.get("status", "ok")
            message = result.get("message", "")
            notice = f"Updated {key} -> {value.strip()} (status: {status})"
            self.app.notify(notice, severity="information")
            summary = f"[green]Config updated[/green] [bold]{key}[/bold]"
            if message:
                summary += f" [dim]{message}[/dim]"
            await log.add_info(summary)
            return

        self.app.notify("Usage: /config [show | set <key> <value>]", severity="warning")

    @staticmethod
    def _parse_positive_int(text: str, *, default: int) -> int:
        """Parse ``text`` as a positive int, falling back to ``default``.

        Used by ``/cron logs`` to accept an optional limit while tolerating
        missing or malformed arguments.
        """
        if not text:
            return default
        try:
            value = int(text)
        except ValueError:
            return default
        return value if value > 0 else default

    def _parse_subcommand(self, args: str) -> tuple[str, str]:
        """Split ``args`` into ``(subcommand, remainder)``.

        Args:
            args: Raw argument string passed to a command handler.

        Returns:
            A tuple of the lower-cased first token and the remainder stripped
            of leading whitespace. Returns ``("", "")`` when ``args`` is empty.
        """
        if not args or not args.strip():
            return "", ""
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""
        return sub, rest

    def _split_kb_flag(self, rest: str) -> tuple[str, str | None]:
        """Extract an optional ``--kb <id>`` flag from a ``/kb search`` arg.

        Args:
            rest: The argument string following ``/kb search``.

        Returns:
            A tuple of the remaining query text and the optional kb id.
        """
        tokens = rest.split()
        kb_id: str | None = None
        query_tokens: list[str] = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            # nosec B105 - CLI flag literal, not a password
            if token == "--kb" and i + 1 < len(tokens):  # nosec B105
                kb_id = tokens[i + 1]
                i += 2
                continue
            query_tokens.append(token)
            i += 1
        return " ".join(query_tokens).strip(), kb_id

    async def _write_http_error(
        self, log: Any, context: str, exc: httpx.HTTPStatusError
    ) -> None:
        """Render an HTTP error as a red system message in the event log.

        Args:
            log: The RichLog widget returned by ``query_one``.
            context: Short description of the failing operation.
            exc: The captured ``httpx.HTTPStatusError``.
        """
        status = exc.response.status_code if exc.response is not None else "?"
        await log.add_info(f"[red]Error ({context}): HTTP {status} - {exc}[/red]")

    def _render_graph_stats(self, stats: dict[str, Any]) -> Table:
        """Build a Rich table summarizing knowledge-graph statistics."""
        table = Table(title="Knowledge Graph Stats", expand=True)
        table.add_column("Metric", style="bold cyan")
        table.add_column("Value", justify="right")

        table.add_row("Total nodes", str(stats.get("total_nodes", 0)))
        table.add_row("Total relationships", str(stats.get("total_relationships", 0)))
        by_type = stats.get("by_type") or {}
        if isinstance(by_type, dict):
            for type_name in sorted(by_type):
                table.add_row(f"  {type_name}", str(by_type[type_name]))
        return table

    def _render_graph_nodes(
        self, nodes: list[dict[str, Any]], node_type: str | None
    ) -> Table:
        """Build a Rich table listing graph nodes."""
        title = f"Graph Nodes ({node_type})" if node_type else "Graph Nodes"
        table = Table(title=title, expand=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Labels", style="magenta")
        table.add_column("Name")

        for node in nodes:
            labels = node.get("labels") or []
            labels_str = ", ".join(labels) if labels else node.get("type", "")
            props = node.get("properties") or {}
            name = (
                props.get("name")
                or props.get("title")
                or props.get("content")
                or node.get("name", "")
            )
            if isinstance(name, str) and len(name) > 80:
                name = name[:77] + "..."
            table.add_row(str(node.get("id", "")), str(labels_str), str(name))
        return table

    def _render_graph_search(self, query: str, hits: list[dict[str, Any]]) -> Table:
        """Build a Rich table of graph-search hits."""
        table = Table(title=f"Graph Search: {query}", expand=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Type", style="magenta")
        table.add_column("Score", justify="right")
        table.add_column("Preview")

        for hit in hits:
            hit_id = str(hit.get("id", ""))
            hit_type = str(hit.get("type") or hit.get("label", ""))
            score = hit.get("score")
            score_str = f"{score:.3f}" if isinstance(score, int | float) else ""
            preview = hit.get("preview") or hit.get("content") or hit.get("name") or ""
            if isinstance(preview, str) and len(preview) > 80:
                preview = preview[:77] + "..."
            table.add_row(hit_id, hit_type, score_str, str(preview))
        return table

    def _render_graph_impact(self, symbol: str, impacts: list[dict[str, Any]]) -> Table:
        """Build a Rich table showing the impact set for ``symbol``."""
        table = Table(title=f"Impact: {symbol}", expand=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Type", style="magenta")
        table.add_column("Path / Name")

        for entry in impacts:
            entry_id = str(entry.get("id", ""))
            entry_type = str(entry.get("type") or entry.get("label", ""))
            target = entry.get("path") or entry.get("name") or entry.get("symbol") or ""
            table.add_row(entry_id, entry_type, str(target))
        return table

    def _render_memory_list(self, memories: list[dict[str, Any]]) -> Table:
        """Build a Rich table listing memory nodes."""
        table = Table(title="Memories", expand=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Importance", justify="right")
        table.add_column("Content")

        for mem in memories:
            props = mem.get("properties") or {}
            mem_id = str(mem.get("id", ""))
            importance = mem.get("importance", props.get("importance"))
            importance_str = (
                f"{importance:.2f}" if isinstance(importance, int | float) else ""
            )
            content = mem.get("content") or props.get("content") or ""
            if isinstance(content, str) and len(content) > 80:
                content = content[:77] + "..."
            table.add_row(mem_id, importance_str, str(content))
        return table

    def _render_memory_detail(self, memory: dict[str, Any]) -> Table:
        """Build a Rich table showing a single memory node's fields."""
        table = Table(title=f"Memory: {memory.get('id', '')}", expand=True)
        table.add_column("Field", style="bold cyan")
        table.add_column("Value")

        for field in ("id", "content", "importance", "created_at", "updated_at"):
            if field in memory:
                table.add_row(field, str(memory[field]))
        tags = memory.get("tags")
        if isinstance(tags, list) and tags:
            table.add_row("tags", ", ".join(str(t) for t in tags))
        return table

    def _render_kb_list(self, kbs: list[dict[str, Any]]) -> Table:
        """Build a Rich table listing knowledge bases."""
        table = Table(title="Knowledge Bases", expand=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="bold")
        table.add_column("Articles", justify="right")
        table.add_column("Status")

        for kb in kbs:
            table.add_row(
                str(kb.get("id", "")),
                str(kb.get("name", "")),
                str(kb.get("article_count", 0)),
                str(kb.get("health_status", "")),
            )
        return table

    def _render_kb_search(
        self, query: str, hits: list[dict[str, Any]], kb_id: str | None
    ) -> Table:
        """Build a Rich table of KB search hits."""
        suffix = f" in {kb_id}" if kb_id else ""
        table = Table(title=f"KB Search: {query}{suffix}", expand=True)
        table.add_column("Article ID", style="cyan", no_wrap=True)
        table.add_column("Title")
        table.add_column("KB", style="magenta")
        table.add_column("Score", justify="right")

        for hit in hits:
            score = hit.get("score")
            score_str = f"{score:.3f}" if isinstance(score, int | float) else ""
            table.add_row(
                str(hit.get("id") or hit.get("article_id", "")),
                str(hit.get("title", "")),
                str(hit.get("kb_id", "")),
                score_str,
            )
        return table

    def _render_kb_article(self, article: dict[str, Any]) -> str:
        """Render a KB article as a markdown-ready string for the event log."""
        title = article.get("title", "Untitled Article")
        kb_id = article.get("kb_id", "")
        content = article.get("content", "")
        header = f"[bold cyan]{title}[/bold cyan]"
        if kb_id:
            header += f"  [dim]({kb_id})[/dim]"
        return f"{header}\n\n{content}"

    def _render_constitution(self, constitution: dict[str, Any]) -> Table:
        """Build a Rich table for the project constitution."""
        table = Table(title="Project Constitution", expand=True)
        table.add_column("Section", style="bold cyan")
        table.add_column("Value")

        rules = constitution.get("governance_rules") or []
        for rule in rules:
            table.add_row("governance_rule", str(rule))

        tech_stack = constitution.get("tech_stack") or {}
        if isinstance(tech_stack, dict):
            for key in sorted(tech_stack):
                table.add_row(f"tech_stack.{key}", str(tech_stack[key]))

        gates = constitution.get("quality_gates") or []
        for gate in gates:
            table.add_row("quality_gate", str(gate))
        return table

    def _render_specs(self, specs: list[dict[str, Any]]) -> Table:
        """Build a Rich table listing SDD specifications."""
        table = Table(title="Specifications", expand=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Title", style="bold")
        table.add_column("Status", style="magenta")
        table.add_column("Created")

        for spec in specs:
            table.add_row(
                str(spec.get("id", "")),
                str(spec.get("title", "")),
                str(spec.get("status", "")),
                str(spec.get("created_at", "")),
            )
        return table

    def _render_plans(self, plans: list[dict[str, Any]]) -> Table:
        """Build a Rich table listing implementation plans."""
        table = Table(title="Implementation Plans", expand=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Spec", style="magenta")
        table.add_column("Status")
        table.add_column("Approach")

        for plan in plans:
            approach = plan.get("technical_approach", "")
            if isinstance(approach, str) and len(approach) > 60:
                approach = approach[:57] + "..."
            table.add_row(
                str(plan.get("id", "")),
                str(plan.get("spec_id", "")),
                str(plan.get("status", "")),
                str(approach),
            )
        return table

    def _render_tasks(self, tasks: list[dict[str, Any]], plan_id: str | None) -> Table:
        """Build a Rich table listing SDD tasks."""
        title = f"Tasks ({plan_id})" if plan_id else "Tasks"
        table = Table(title=title, expand=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Plan", style="magenta")
        table.add_column("Title", style="bold")
        table.add_column("Status")
        table.add_column("Parallel", justify="right")

        for task in tasks:
            table.add_row(
                str(task.get("id", "")),
                str(task.get("plan_id", "")),
                str(task.get("title", "")),
                str(task.get("status", "")),
                "yes" if task.get("parallel") else "no",
            )
        return table

    def _render_impact_table(self, symbol: str, impacts: list[dict[str, Any]]) -> Table:
        """Build a Rich table for ``/impact`` output."""
        table = Table(title=f"Impact: {symbol}", expand=True)
        table.add_column("Name", style="bold cyan")
        table.add_column("Type", style="magenta")
        table.add_column("File")
        table.add_column("Depth", justify="right")
        table.add_column("Relationship")

        for entry in impacts:
            props = entry.get("properties") or {}
            name = (
                entry.get("name")
                or props.get("name")
                or entry.get("symbol")
                or props.get("symbol")
                or str(entry.get("id", ""))
            )
            node_type = (
                entry.get("type")
                or entry.get("label")
                or (entry.get("labels") or [""])[0]
                or props.get("type", "")
            )
            file_path = (
                entry.get("file")
                or entry.get("path")
                or props.get("file")
                or props.get("path")
                or ""
            )
            depth = entry.get("depth") or entry.get("distance")
            depth_str = str(depth) if depth is not None else ""
            relationship = (
                entry.get("relationship")
                or entry.get("rel_type")
                or entry.get("edge_type")
                or ""
            )
            table.add_row(
                str(name),
                str(node_type),
                str(file_path),
                depth_str,
                str(relationship),
            )
        return table

    def _render_resources_table(self, resources: list[dict[str, Any]]) -> Table:
        """Build a Rich table listing callable resources."""
        table = Table(title="Callable Resources", expand=True)
        table.add_column("Type", style="magenta", no_wrap=True)
        table.add_column("Name", style="bold cyan")
        table.add_column("Description")

        for resource in resources:
            r_type = (
                resource.get("type")
                or resource.get("resource_type")
                or resource.get("kind", "")
            )
            name = resource.get("name") or resource.get("id", "")
            description = resource.get("description", "")
            if isinstance(description, str) and len(description) > 80:
                description = description[:77] + "..."
            table.add_row(str(r_type), str(name), str(description))
        return table

    def _render_pipeline_status(self, status: dict[str, Any]) -> Table:
        """Build a Rich table of pipeline-phase status."""
        title = f"Pipeline ({status.get('status', 'unknown')})"
        table = Table(title=title, expand=True)
        table.add_column("Phase", style="bold cyan", no_wrap=True)
        table.add_column("State", style="magenta")
        table.add_column("Last Run")
        table.add_column("Progress", justify="right")

        phases = status.get("phases") or []
        if isinstance(phases, dict):
            phases = [
                {"name": name, **(info if isinstance(info, dict) else {})}
                for name, info in phases.items()
            ]
        for phase in phases:
            name = phase.get("name") or phase.get("phase", "")
            state = phase.get("state") or phase.get("status", "")
            last_run = phase.get("last_run") or phase.get("last_executed", "")
            progress = phase.get("progress")
            progress_str = (
                f"{progress * 100:.0f}%"
                if isinstance(progress, int | float) and progress <= 1
                else str(progress)
                if progress is not None
                else ""
            )
            table.add_row(str(name), str(state), str(last_run), progress_str)
        return table

    def _render_maintenance_status(self, status: dict[str, Any]) -> Table:
        """Build a Rich table of maintenance-operation status."""
        title = f"Maintenance ({status.get('status', 'unknown')})"
        table = Table(title=title, expand=True)
        table.add_column("Operation", style="bold cyan", no_wrap=True)
        table.add_column("Last Run")
        table.add_column("Items Pruned", justify="right")
        table.add_column("Items Updated", justify="right")

        operations = status.get("operations") or []
        if isinstance(operations, dict):
            operations = [
                {"name": name, **(info if isinstance(info, dict) else {})}
                for name, info in operations.items()
            ]
        for operation in operations:
            name = operation.get("name") or operation.get("operation", "")
            last_run = operation.get("last_run") or operation.get("last_executed", "")
            pruned = operation.get("items_pruned", operation.get("pruned", 0))
            updated = operation.get("items_updated", operation.get("updated", 0))
            table.add_row(str(name), str(last_run), str(pruned), str(updated))
        return table

    def _render_cron_calendar(self, tasks: list[dict[str, Any]]) -> Table:
        """Build a Rich table of scheduled cron tasks."""
        table = Table(title="Cron Calendar", expand=True)
        table.add_column("Name", style="bold cyan")
        table.add_column("Schedule", style="magenta")
        table.add_column("Next Run")
        table.add_column("Last Run")
        table.add_column("Status")

        for task in tasks:
            name = task.get("name") or task.get("task_name") or task.get("id", "")
            schedule = (
                task.get("schedule")
                or task.get("cron")
                or task.get("cron_expression", "")
            )
            next_run = task.get("next_run") or task.get("next_execution", "")
            last_run = task.get("last_run") or task.get("last_execution", "")
            status = task.get("status") or task.get("state", "")
            table.add_row(
                str(name),
                str(schedule),
                str(next_run),
                str(last_run),
                str(status),
            )
        return table

    def _render_cron_logs(self, logs: list[dict[str, Any]], limit: int) -> Table:
        """Build a Rich table summarizing recent cron executions."""
        table = Table(title=f"Cron Logs (latest {limit})", expand=True)
        table.add_column("Name", style="bold cyan")
        table.add_column("Started", style="magenta")
        table.add_column("Duration", justify="right")
        table.add_column("Status")
        table.add_column("Output")

        for entry in logs:
            name = (
                entry.get("task_name") or entry.get("name") or entry.get("task_id", "")
            )
            started = (
                entry.get("started_at")
                or entry.get("timestamp")
                or entry.get("start_time", "")
            )
            duration = entry.get("duration") or entry.get("duration_ms", "")
            if isinstance(duration, int | float):
                duration_str = f"{duration}"
            else:
                duration_str = str(duration) if duration else ""
            status = entry.get("status") or entry.get("result", "")
            output = entry.get("output") or entry.get("message", "")
            if isinstance(output, str) and len(output) > 80:
                output = output[:77] + "..."
            table.add_row(
                str(name),
                str(started),
                duration_str,
                str(status),
                str(output),
            )
        return table

    def _render_backend_config(self, config: dict[str, Any]) -> Panel:
        """Render backend configuration as a Rich Panel of key/value lines."""
        if not config:
            return Panel(
                "[yellow]No backend configuration reported.[/yellow]",
                title="Backend Config",
                expand=True,
            )
        lines: list[str] = []
        for key in sorted(config):
            value = config[key]
            if isinstance(value, dict):
                lines.append(f"[bold cyan]{key}[/bold cyan]:")
                for sub_key in sorted(value):
                    lines.append(f"  [cyan]{sub_key}[/cyan] = {value[sub_key]}")
            else:
                lines.append(f"[bold cyan]{key}[/bold cyan] = {value}")
        return Panel(
            "\n".join(lines),
            title="Backend Config",
            expand=True,
        )

    # ─────────────────────────────────────────────────────────────────
    #  KG-Native Commands (CONCEPT:KG-002 / KG-003)
    # ─────────────────────────────────────────────────────────────────

    async def cmd_prompts(self, args: str) -> None:
        """Manage system prompts: list, get, set, versions, rollback, add."""
        parts = args.strip().split(maxsplit=2)
        subcmd = parts[0].lower() if parts else ""

        if not subcmd or subcmd == "list":
            prompts = await self.app._client.list_prompts()
            if not prompts:
                await self.app.query_one("Conversation").add_info(
                    "[yellow]No prompts found in KG.[/yellow]"
                )
                return
            table = Table(title="Prompts (CONCEPT:KG-002)", expand=True)
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Name", style="bold")
            table.add_column("Description")
            table.add_column("Version", justify="right")
            for p in prompts:
                table.add_row(
                    str(p.get("id", "")),
                    str(p.get("name", "")),
                    str(p.get("description", ""))[:60],
                    str(p.get("version_number", "1")),
                )
            await self.app.query_one("Conversation").add_info(table)

        elif subcmd == "get" and len(parts) >= 2:
            prompt = await self.app._client.get_prompt(parts[1])
            content = prompt.get("content", "")
            syntax = Syntax(content, "markdown", theme="monokai")
            await self.app.query_one("Conversation").add_info(
                Panel(syntax, title=f"Prompt: {prompt.get('name', parts[1])}")
            )

        elif subcmd == "set" and len(parts) >= 3:
            result = await self.app._client.update_prompt(parts[1], parts[2])
            version = result.get("version_number", "?")
            await self.app.query_one("Conversation").add_info(
                f"[green]✓ Updated prompt → version {version}[/green]"
            )

        elif subcmd == "versions" and len(parts) >= 2:
            versions = await self.app._client.get_prompt_versions(parts[1])
            if not versions:
                await self.app.query_one("Conversation").add_info(
                    "[yellow]No versions found.[/yellow]"
                )
                return
            table = Table(title=f"Version History: {parts[1]}", expand=True)
            table.add_column("Version", justify="right")
            table.add_column("ID", style="cyan")
            table.add_column("Author")
            table.add_column("Timestamp")
            for v in versions:
                table.add_row(
                    str(v.get("version_number", "?")),
                    str(v.get("id", "")),
                    str(v.get("author", "")),
                    str(v.get("timestamp", "")),
                )
            await self.app.query_one("Conversation").add_info(table)

        elif subcmd == "rollback" and len(parts) >= 3:
            result = await self.app._client.rollback_prompt(parts[1], parts[2])
            version = result.get("version_number", "?")
            await self.app.query_one("Conversation").add_info(
                f"[green]✓ Rolled back to version {version}[/green]"
            )

        elif subcmd == "add" and len(parts) >= 3:
            name = parts[1]
            content = parts[2]
            result = await self.app._client.create_prompt(name, content)
            prompt_name = result.get("name", name)
            prompt_id = result.get("id", "?")
            await self.app.query_one("Conversation").add_info(
                f"[green]✓ Created prompt '{prompt_name}' ({prompt_id})[/green]"
            )

        else:
            await self.app.query_one("Conversation").add_info(
                "[bold blue]Usage:[/bold blue]\n"
                "  /prompts                     — list all prompts\n"
                "  /prompts get <id>             — show prompt content\n"
                "  /prompts set <id> <content>   — update prompt\n"
                "  /prompts versions <id>        — show version history\n"
                "  /prompts rollback <id> <ver>  — rollback to version\n"
                "  /prompts add <name> <content> — create new prompt"
            )

    async def cmd_skills_only(self, args: str) -> None:
        """List and manage agent skills (pre-baked capabilities)."""
        parts = args.strip().split(maxsplit=1)
        subcmd = parts[0].lower() if parts else ""

        if subcmd == "toggle" and len(parts) >= 2:
            result = await self.app._client.toggle_resource(parts[1])
            status = "enabled" if result.get("enabled") else "disabled"
            await self.app.query_one("Conversation").add_info(
                f"[green]✓ {parts[1]} is now {status}[/green]"
            )
            return

        skills = await self.app._client.list_skills_only()
        if not skills:
            await self.app.query_one("Conversation").add_info(
                "[yellow]No skills discovered.[/yellow]"
            )
            return
        table = Table(title="Agent Skills (CONCEPT:KG-003)", expand=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="bold")
        table.add_column("Source")
        table.add_column("Enabled", justify="center")
        for s in skills:
            enabled = "✅" if s.get("enabled", True) else "❌"
            table.add_row(
                str(s.get("id", "")),
                str(s.get("name", "")),
                str(s.get("source", "custom")),
                enabled,
            )
        await self.app.query_one("Conversation").add_info(table)

    async def cmd_tools_only(self, args: str) -> None:
        """List and manage MCP tools."""
        parts = args.strip().split(maxsplit=1)
        subcmd = parts[0].lower() if parts else ""

        if subcmd == "toggle" and len(parts) >= 2:
            result = await self.app._client.toggle_resource(parts[1])
            status = "enabled" if result.get("enabled") else "disabled"
            await self.app.query_one("Conversation").add_info(
                f"[green]✓ {parts[1]} is now {status}[/green]"
            )
            return

        tools = await self.app._client.list_tools_only()
        if not tools:
            await self.app.query_one("Conversation").add_info(
                "[yellow]No MCP tools discovered.[/yellow]"
            )
            return
        table = Table(title="MCP Tools (CONCEPT:KG-003)", expand=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="bold")
        table.add_column("Server/Source")
        table.add_column("Enabled", justify="center")
        for t in tools:
            enabled = "✅" if t.get("enabled", True) else "❌"
            table.add_row(
                str(t.get("id", "")),
                str(t.get("name", "")),
                str(t.get("source", t.get("endpoint", "unknown"))),
                enabled,
            )
        await self.app.query_one("Conversation").add_info(table)
