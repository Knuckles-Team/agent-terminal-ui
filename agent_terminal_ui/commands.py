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
from rich.console import Group
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
            "usage": self.cmd_usage,
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
            "ask": self.cmd_ask,
            "nl": self.cmd_nl,
            "obs": self.cmd_obs,
            "broker": self.cmd_broker,
            "kvcache": self.cmd_kvcache,
            "ingest": self.cmd_ingest,
            "kb": self.cmd_kb,
            "sdd": self.cmd_sdd,
            "impact": self.cmd_impact,
            "fleet": self.cmd_fleet,
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
            "capabilities": self.cmd_capabilities,
            "capability": self.cmd_capabilities,
            "run": self.cmd_run,
            "runs": self.cmd_run,
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
            "capability": "capabilities",
            "runs": "run",
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
            await self._run_registered_command(cmd_name, args)
        else:
            await self._run_gateway_command(cmd_name, text)
        return True

    async def _run_registered_command(self, cmd_name: str, args: str) -> None:
        """Invoke a locally registered command, surfacing failures as notices."""
        try:
            await self.commands[cmd_name](args)
        except Exception as e:
            self.app.notify(
                f"Error executing command /{cmd_name}: {e}", severity="error"
            )

    async def _run_gateway_command(self, cmd_name: str, text: str) -> None:
        """Fall back to the gateway's commands/execute endpoint."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.app.agent_client.base_url}/api/enhanced/commands/execute",
                    json={"command": text},
                    timeout=15.0,
                )
                if response.status_code != 200:
                    self.app.notify(
                        f"Gateway command failed: Code {response.status_code}",
                        severity="error",
                    )
                    return
                data = response.json()
                await self._show_gateway_response(data.get("response_markdown", ""))
                await self._apply_client_actions(data.get("client_actions", []))
        except Exception as e:
            self.app.notify(
                f"Unknown command: /{cmd_name} (Gateway offline: {e})",
                severity="warning",
            )

    async def _show_gateway_response(self, response_markdown: str) -> None:
        """Render a gateway response in the conversation, or notify on failure."""
        try:
            conv = self.app.query_one("Conversation")
            await conv.add_agent_response(response_markdown)
        except Exception:
            self.app.notify(response_markdown[:100], severity="information")

    async def _apply_client_actions(self, client_actions: list[Any]) -> None:
        """Apply the client-side actions requested by a gateway response."""
        for action_dict in client_actions:
            if action_dict.get("action") != "clear_chat":
                continue
            with contextlib.suppress(Exception):
                conv = self.app.query_one("Conversation")
                await conv.clear_conversation()
                await conv.add_info("🧹 Chat log cleared via slash command.")

    async def cmd_help(self, args: str) -> None:
        """Show available commands and their descriptions."""
        # CONCEPT:AU-ECO.messaging.shared-by-every-messaging
        # Cross-surface descriptions come from the one agent-utilities command
        # registry; TUI-only commands fall back to their handler docstring.
        try:
            from agent_utilities.messaging.commands import command_specs

            registry = {
                c["command"]: c["description"] for c in command_specs("terminal")
            }
        except Exception:  # noqa: BLE001 — registry optional; never break /help
            registry = {}
        help_text = "[bold blue]Available Commands:[/bold blue]\n"
        for cmd in sorted(self.commands.keys()):
            doc = registry.get(cmd) or self.commands[cmd].__doc__ or "No description"
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

    async def cmd_capabilities(self, args: str) -> None:
        """Search live capabilities. Usage: /capabilities [query]"""
        opener = getattr(self.app, "open_capability_palette", None)
        if not callable(opener):
            self.app.notify("Capability palette unavailable.", severity="warning")
            return
        opener(initial_query=args.strip())

    async def cmd_run(self, args: str) -> None:
        """Browse runs or follow one in Mission Control. Usage: /run [run_id]"""
        run_id = args.strip() or getattr(self.app, "last_run_id", None)
        opener = getattr(self.app, "open_run_inspector", None)
        if not callable(opener):
            self.app.notify("Run inspector unavailable.", severity="warning")
            return
        opener(str(run_id) if run_id else None)

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
        """Show live token/cost stats for the current session.

        CONCEPT:AU-ECO.mcp.usage-cost-observability-surface
        """
        tracker = getattr(self.app, "cost_tracker", None)
        if tracker is not None:
            with contextlib.suppress(Exception):
                s = tracker.get_session_summary()
                stats = (
                    f"[bold blue]This session (live):[/bold blue]\n"
                    f"- Turns: {s.total_turns}\n"
                    f"- Tokens: {s.total_input_tokens} in / "
                    f"{s.total_output_tokens} out\n"
                    f"- Cache hit: {s.cache_hit_rate * 100:.0f}%\n"
                    f"- Cost: ${s.total_cost_usd:.4f}\n"
                    f"[dim]Run /usage (or Alt+U) for cross-agent history.[/dim]"
                )
                await self.app.query_one("Conversation").add_info(stats)
                return
        # Fallback to any server-provided usage snapshot.
        usage = getattr(self.app, "_last_usage", None)
        if usage:
            stats = (
                f"[bold blue]Session Statistics:[/bold blue]\n"
                f"- Total Tokens: {usage.get('total_tokens', 0)}\n"
                f"- Estimated Cost: ${usage.get('estimated_cost_usd', 0):.4f}\n"
            )
        else:
            stats = (
                "[yellow]No usage yet. Run /usage (Alt+U) for the full "
                "cross-agent dashboard.[/yellow]"
            )
        await self.app.query_one("Conversation").add_info(stats)

    async def cmd_usage(self, args: str) -> None:
        """Open the full Usage & Cost dashboard (live + cross-agent history)."""
        action = getattr(self.app, "action_switch_usage", None)
        if action is not None:
            action()
        else:
            await self.cmd_stats(args)

    async def cmd_ingest(self, args: str) -> None:
        """Extract a knowledge graph from a URL, file, or text (live).

        Usage:
            /ingest <url>              extract from a web page (readability)
            /ingest <path>             extract from a local file
            /ingest -- <text>          extract from inline text
            /ingest jsonl <job_id>     download a finished job's facts as JSONL

        Facts stream in live as (subject)-[predicate]->(object) rows with
        confidence, tags, and evidence. Backed by the GPU-slot scheduler
        (ECO-4.43).
        """
        conversation = self.app.query_one("Conversation")
        client = getattr(self.app, "agent_client", None)
        if client is None:
            await conversation.add_info(
                "[yellow]/ingest requires an agent backend connection.[/yellow]"
            )
            return

        raw = args.strip()
        if not raw:
            await conversation.add_info(
                "[yellow]Usage: /ingest <url|path>  |  /ingest -- <text>  |  "
                "/ingest jsonl <job_id>[/yellow]"
            )
            return

        parts = raw.split(maxsplit=1)
        if parts[0] == "jsonl":
            await self._ingest_export_jsonl(conversation, client, parts)
            return

        text, url = self._ingest_source(raw, parts)
        job_id = await self._ingest_submit(conversation, client, text, url)
        if job_id is None:
            return
        await self._ingest_stream_facts(conversation, client, job_id)

    async def _ingest_export_jsonl(
        self, conversation: Any, client: Any, parts: list[str]
    ) -> None:
        """Download a finished extraction job's facts as JSONL."""
        if len(parts) < 2:
            await conversation.add_info(
                "[yellow]Usage: /ingest jsonl <job_id>[/yellow]"
            )
            return
        job_id = parts[1].strip()
        try:
            jsonl = await client.extraction_jsonl(job_id)
        except Exception as exc:
            await conversation.add_info(f"[red]JSONL fetch failed: {exc}[/red]")
            return
        lines = jsonl.strip().splitlines()
        await conversation.add_info(
            f"[green]{len(lines)} facts[/green] (job {job_id}):\n"
            + "\n".join(f"[dim]{ln}[/dim]" for ln in lines[:50])
            + ("\n…" if len(lines) > 50 else "")
        )

    @staticmethod
    def _ingest_source(raw: str, parts: list[str]) -> tuple[str, str]:
        """Resolve ``/ingest`` arguments into an ``(inline text, url)`` pair."""
        if parts[0] == "--":
            return (parts[1] if len(parts) > 1 else ""), ""
        if raw.startswith(("http://", "https://")):
            return "", raw

        from pathlib import Path

        p = Path(raw).expanduser()
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="ignore"), ""
        return "", raw  # let the gateway's reader try it as a URL

    async def _ingest_submit(
        self, conversation: Any, client: Any, text: str, url: str
    ) -> str | None:
        """Submit an extraction job, returning its id or ``None`` on failure."""
        try:
            res = await client.submit_extraction(text=text, url=url)
        except Exception as exc:
            await conversation.add_info(f"[red]Extraction submit failed: {exc}[/red]")
            return None
        job_id = res.get("job_id")
        if res.get("status") != "submitted" or not job_id:
            msg = res.get("message", "engine cold?")
            await conversation.add_info(
                f"[yellow]Extraction unavailable: {msg}[/yellow]"
            )
            return None

        await conversation.add_info(
            f"[bold blue]Extracting[/bold blue] (job [cyan]{job_id}[/cyan])… "
            "facts stream below; `/ingest jsonl " + job_id + "` to export."
        )
        return job_id

    async def _ingest_stream_facts(
        self, conversation: Any, client: Any, job_id: str
    ) -> None:
        """Stream extracted facts into the conversation until the job ends."""
        kept = 0
        dupes = 0
        try:
            async for ev in client.stream_extraction(job_id):
                etype = ev.get("type")
                if etype == "job_done":
                    break
                if etype != "fact":
                    continue
                if ev.get("is_duplicate"):
                    dupes += 1
                    continue
                kept += 1
                await conversation.add_info(self._format_fact_row(ev.get("fact", {})))
        except Exception as exc:
            await conversation.add_info(f"[red]Stream error: {exc}[/red]")
            return

        await conversation.add_info(
            f"[green]Done[/green] — {kept} facts"
            + (f" ([dim]{dupes} duplicates suppressed[/dim])" if dupes else "")
            + f". Export: /ingest jsonl {job_id}"
        )

    @staticmethod
    def _format_fact_row(fact: dict[str, Any]) -> str:
        """Render one extracted fact as a colourised conversation row."""
        tags = " ".join(f"#{t}" for t in (fact.get("tags") or [])[:4])
        conf = fact.get("confidence", "–")
        return (
            f"[blue]{fact.get('subject', '')}[/blue] "
            f"[magenta]{fact.get('predicate', '')}[/magenta] "
            f"[green]{fact.get('object', '')}[/green]  "
            f"[dim]conf {conf}%  {tags}[/dim]"
        )

    async def _fleet_grant(
        self, conversation: Any, client: Any, parts: list[str]
    ) -> None:
        """``/fleet grant <approval_id>`` — approve one pending fleet action."""
        if len(parts) < 2:
            await conversation.add_info(
                "[yellow]Usage: /fleet grant <approval_id>[/yellow]"
            )
            return
        try:
            await client.grant_fleet_approval(parts[1])
        except Exception as exc:
            await conversation.add_info(f"[red]Grant failed: {exc}[/red]")
            return
        await conversation.add_info(f"[green]Granted approval {parts[1]}.[/green]")

    @staticmethod
    def _fleet_lines(topology: Any, approvals: list[dict[str, Any]]) -> list[str]:
        """Format the fleet topology and pending-approval summary lines."""
        lines = ["[bold blue]Fleet Supervisor[/bold blue]"]
        if topology:
            lines.append("[bold]Topology[/bold]")
            lines.extend(f"- {key}: {value}" for key, value in topology.items())
        lines.append(f"[bold]Pending approvals:[/bold] {len(approvals)}")
        for approval in approvals:
            approval_id = approval.get("id") or approval.get("approval_id") or "?"
            action = approval.get("action", "")
            target = approval.get("target") or approval.get("subject") or ""
            lines.append(f"- {approval_id}: {action} {target}".rstrip())
        if approvals:
            lines.append("[dim]Grant with /fleet grant <id>[/dim]")
        return lines

    async def _fleet_overview(self, conversation: Any, client: Any) -> None:
        """Render fleet topology plus the pending-approval queue."""
        try:
            topology = await client.get_fleet_topology()
            approvals = await client.get_fleet_approvals()
        except Exception as exc:
            await conversation.add_info(f"[red]Fleet unavailable: {exc}[/red]")
            return
        await conversation.add_info("\n".join(self._fleet_lines(topology, approvals)))

    async def cmd_fleet(self, args: str) -> None:
        """Show fleet topology and approvals, or grant one with ``grant <id>``."""
        conversation = self.app.query_one("Conversation")
        client = getattr(self.app, "agent_client", None)
        if client is None:
            await conversation.add_info(
                "[yellow]Fleet view requires an agent backend connection.[/yellow]"
            )
            return

        parts = args.strip().split()
        if parts and parts[0] == "grant":
            await self._fleet_grant(conversation, client, parts)
            return
        await self._fleet_overview(conversation, client)

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

    def _active_model_id(self, registry: dict[str, Any]) -> Any:
        """Resolve the active model id from app state, falling back to default."""
        return (
            getattr(self.app, "_current_model_id", None)
            or getattr(self.app, "_current_model", None)
            or registry.get("default_id")
        )

    @staticmethod
    def _model_cost_pair(entry: dict[str, Any]) -> tuple[float, float]:
        """Return the (input, output) cost per 1M tokens for a model entry."""
        cost = entry.get("cost") or {}
        return float(cost.get("input", 0.0)), float(cost.get("output", 0.0))

    def _model_row(self, entry: dict[str, Any], active_id: Any) -> list[str]:
        """Build the registry-table cells for one configured model."""
        cost_in, cost_out = self._model_cost_pair(entry)
        return [
            "*" if entry.get("id") == active_id else "",
            str(entry.get("id", "")),
            str(entry.get("name", "")),
            str(entry.get("provider", "")),
            str(entry.get("tier", "")),
            ", ".join(entry.get("tags") or []) or "-",
            "yes" if entry.get("is_default") else "",
            f"${cost_in:.2f} / ${cost_out:.2f}",
        ]

    async def _model_list(self) -> None:
        """Render the configured model registry as a Rich table."""
        registry = await self.app._client.list_configured_models()
        models = registry.get("models") or []
        active_id = self._active_model_id(registry)

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

        for entry in models:
            table.add_row(*self._model_row(entry, active_id))

        event_log = self.app.query_one("Conversation")
        await event_log.add_info(table)
        await event_log.add_info(
            "[dim]Use `/model set <id>` to switch, `/model show` to inspect.[/dim]"
        )

    def _model_panel(self, match: dict[str, Any]) -> Panel:
        """Build the detail panel for the currently active model."""
        cost_in, cost_out = self._model_cost_pair(match)
        return Panel(
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

    async def _model_show(self) -> None:
        """Display the currently active model, resolving the backend default."""
        registry = await self.app._client.list_configured_models()
        models = registry.get("models") or []
        active_id = self._active_model_id(registry)
        match = next((m for m in models if m.get("id") == active_id), None)

        if match is None:
            await self.app.query_one("Conversation").add_info(
                "[yellow]No active model. "
                "Run `/model list` to see what is configured.[/yellow]"
            )
            return

        await self.app.query_one("Conversation").add_info(self._model_panel(match))

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

    def _require_arg(self, rest: str, usage: str) -> str | None:
        """Return the stripped argument, or ``None`` after notifying the usage."""
        value = rest.strip()
        if not value:
            self.app.notify(usage, severity="warning")
            return None
        return value

    async def _memory_list(self, log: Any, rest: str) -> None:
        """``/memory list`` — render every Memory node."""
        try:
            memories = await self.app._client.list_graph_nodes(node_type="Memory")
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "memory list", exc)
            return
        await log.add_info(self._render_memory_list(memories))

    async def _memory_add(self, log: Any, rest: str) -> None:
        """``/memory add <content>`` — create a Memory node."""
        content = self._require_arg(rest, "Usage: /memory add <content>")
        if content is None:
            return
        try:
            created = await self.app._client.create_memory({"content": content})
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "memory add", exc)
            return
        mem_id = created.get("id", "<unknown>")
        self.app.notify(f"Memory created: {mem_id}", severity="information")
        await log.add_info(f"[green]Memory created:[/green] {mem_id}")

    async def _memory_get(self, log: Any, rest: str) -> None:
        """``/memory get <id>`` — render one Memory node."""
        mem_id = self._require_arg(rest, "Usage: /memory get <id>")
        if mem_id is None:
            return
        try:
            memory = await self.app._client.get_memory(mem_id)
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "memory get", exc)
            return
        await log.add_info(self._render_memory_detail(memory))

    async def _memory_delete(self, log: Any, rest: str) -> None:
        """``/memory delete <id>`` — remove one Memory node."""
        mem_id = self._require_arg(rest, "Usage: /memory delete <id>")
        if mem_id is None:
            return
        try:
            await self.app._client.delete_memory(mem_id)
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "memory delete", exc)
            return
        self.app.notify(f"Memory deleted: {mem_id}", severity="warning")
        await log.add_info(f"[yellow]Memory deleted:[/yellow] {mem_id}")

    async def _memory_search(self, log: Any, rest: str) -> None:
        """``/memory search <query>`` — semantic search across the graph."""
        query = self._require_arg(rest, "Usage: /memory search <query>")
        if query is None:
            return
        try:
            hits = await self.app._client.search_graph(query)
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "memory search", exc)
            return
        await log.add_info(self._render_graph_search(query, hits))

    async def _memory_review(self, log: Any, rest: str) -> None:
        """``/memory review`` — ask the agent to summarize stored memories."""
        await self._submit_prompt(
            "Review the current knowledge-graph memories and summarize key items."
        )

    async def cmd_memory(self, args: str) -> None:
        """Manage knowledge-graph memory nodes.

        Usage: /memory [list | add <content> | get <id> | delete <id>
                        | search <query> | review | <prompt>]
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")
        handlers: dict[str, Callable[[Any, str], Awaitable[None]]] = {
            "": self._memory_list,
            "list": self._memory_list,
            "add": self._memory_add,
            "get": self._memory_get,
            "delete": self._memory_delete,
            "search": self._memory_search,
            "review": self._memory_review,
        }
        handler = handlers.get(sub)
        if handler is None:
            await self._submit_prompt(f"Manage project memory: {args}")
            return
        await handler(log, rest)

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

        from agent_terminal_ui.goal import GoalSpec

        spec = GoalSpec.parse_goal_input(args)
        spec.session_id = getattr(self.app, "current_session_id", None) or ""

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
        session_id = getattr(self.app, "current_session_id", None)
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

    async def _graph_stats(self, log: Any, rest: str) -> None:
        """``/graph stats`` — summarize the knowledge graph."""
        try:
            stats = await self.app._client.get_graph_stats()
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "graph stats", exc)
            return
        await log.add_info(self._render_graph_stats(stats))

    async def _graph_nodes(self, log: Any, rest: str) -> None:
        """``/graph nodes [type]`` — list graph nodes, optionally by type."""
        node_type = rest.strip() or None
        try:
            nodes = await self.app._client.list_graph_nodes(node_type=node_type)
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "graph nodes", exc)
            return
        await log.add_info(self._render_graph_nodes(nodes, node_type))

    async def _graph_search(self, log: Any, rest: str) -> None:
        """``/graph search <query>`` — semantic search across the graph."""
        query = self._require_arg(rest, "Usage: /graph search <query>")
        if query is None:
            return
        try:
            hits = await self.app._client.search_graph(query)
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "graph search", exc)
            return
        await log.add_info(self._render_graph_search(query, hits))

    async def _graph_impact(self, log: Any, rest: str) -> None:
        """``/graph impact <symbol>`` — show what a symbol change would touch."""
        symbol = self._require_arg(rest, "Usage: /graph impact <symbol>")
        if symbol is None:
            return
        try:
            impacts = await self.app._client.get_graph_impact(symbol)
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "graph impact", exc)
            return
        await log.add_info(self._render_graph_impact(symbol, impacts))

    async def cmd_graph(self, args: str) -> None:
        """Explore the knowledge graph.

        Usage: /graph [stats | nodes [type] | search <query> | impact <symbol>]
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")
        handlers: dict[str, Callable[[Any, str], Awaitable[None]]] = {
            "": self._graph_stats,
            "stats": self._graph_stats,
            "nodes": self._graph_nodes,
            "search": self._graph_search,
            "impact": self._graph_impact,
        }
        handler = handlers.get(sub)
        if handler is None:
            self.app.notify(f"Unknown /graph subcommand: {sub}", severity="warning")
            return
        await handler(log, rest)

    async def cmd_ask(self, args: str) -> None:
        """Ask a data question in plain English (multi-step analyst, KG-2.308).

        Usage: /ask <natural-language question>
        """
        question = args.strip()
        if not question:
            self.app.notify("Usage: /ask <question>", severity="warning")
            return
        log = self.app.query_one("Conversation")
        await log.add_info(f"[dim]Asking the data analyst: {question}[/dim]")
        try:
            result = await self.app._client.graph_ask_data(question)
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "ask", exc)
            return
        await log.add_info(self._render_ask_data(result))

    async def cmd_nl(self, args: str) -> None:
        """Translate a question into a graph query and run it (KG-2.305).

        Usage: /nl <question>  (prefix with 'preview ' to dry-run the query)
        """
        text = args.strip()
        if not text:
            self.app.notify("Usage: /nl <question>", severity="warning")
            return
        execute = True
        sub, rest = self._parse_subcommand(text)
        if sub == "preview" and rest.strip():
            execute = False
            text = rest.strip()
        log = self.app.query_one("Conversation")
        try:
            result = await self.app._client.graph_nl_query(text, execute=execute)
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "nl-query", exc)
            return
        await log.add_info(self._render_nl_query(result))

    async def cmd_obs(self, args: str) -> None:
        """Query observability metrics (PromQL) and traces (KG-2.310).

        Usage: /obs <promql>            instant metric evaluation
               /obs range <promql>      range query with a sparkline
               /obs traces [service]    search recent distributed traces
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")

        if sub == "traces":
            service = rest.strip()
            try:
                result = await self.app._client.graph_traces(service=service)
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "traces", exc)
                return
            await log.add_info(self._render_traces(result))
            return

        if sub == "range":
            expr = rest.strip()
            if not expr:
                self.app.notify("Usage: /obs range <promql>", severity="warning")
                return
            try:
                result = await self.app._client.graph_promql(
                    expr, action="range", start="-15m", end="now", step="30s"
                )
            except httpx.HTTPStatusError as exc:
                await self._write_http_error(log, "promql", exc)
                return
            await log.add_info(self._render_promql(result, expr, "range"))
            return

        expr = args.strip()
        if sub == "metric":
            expr = rest.strip()
        if not expr:
            self.app.notify(
                "Usage: /obs <promql> | range <promql> | traces [service]",
                severity="warning",
            )
            return
        try:
            result = await self.app._client.graph_promql(expr, action="instant")
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "promql", exc)
            return
        await log.add_info(self._render_promql(result, expr, "instant"))

    async def cmd_broker(self, args: str) -> None:
        """Show engine message-broker status (KG-2.310).

        Usage: /broker [stats | queues | exchanges]
        """
        sub, _ = self._parse_subcommand(args)
        action = {
            "": "stats",
            "stats": "stats",
            "queues": "list_queues",
            "exchanges": "list_exchanges",
        }.get(sub)
        if action is None:
            self.app.notify(f"Unknown /broker subcommand: {sub}", severity="warning")
            return
        log = self.app.query_one("Conversation")
        try:
            result = await self.app._client.graph_broker(action=action)
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "broker", exc)
            return
        await log.add_info(self._render_broker(result, action))

    async def cmd_kvcache(self, args: str) -> None:
        """Show shared KV-cache occupancy and dedup stats (KG-2.306/2.310)."""
        log = self.app.query_one("Conversation")
        try:
            result = await self.app._client.graph_kvcache(action="stats")
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "kvcache", exc)
            return
        await log.add_info(self._render_kvcache(result))

    async def _kb_list(self, log: Any, rest: str) -> None:
        """``/kb list`` — show every knowledge base."""
        try:
            kbs = await self.app._client.list_kbs()
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "kb list", exc)
            return
        await log.add_info(self._render_kb_list(kbs))

    async def _kb_search(self, log: Any, rest: str) -> None:
        """``/kb search <query> [--kb <id>]`` — search knowledge-base articles."""
        usage = "Usage: /kb search <query> [--kb <id>]"
        if self._require_arg(rest, usage) is None:
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

    async def _kb_article(self, log: Any, rest: str) -> None:
        """``/kb article <id>`` — render one knowledge-base article."""
        article_id = self._require_arg(rest, "Usage: /kb article <article_id>")
        if article_id is None:
            return
        try:
            article = await self.app._client.get_kb_article(article_id)
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "kb article", exc)
            return
        await log.add_info(self._render_kb_article(article))

    async def _kb_ingest(self, log: Any, rest: str) -> None:
        """``/kb ingest <source> <kb_name>`` — ingest a source into a KB."""
        parts = rest.split(maxsplit=1)
        if len(parts) < 2:
            self.app.notify("Usage: /kb ingest <source> <kb_name>", severity="warning")
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

    async def cmd_kb(self, args: str) -> None:
        """Browse and ingest knowledge bases.

        Usage: /kb [list | search <query> [--kb <id>]
                    | article <id> | ingest <source> <kb_name>]
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")
        handlers: dict[str, Callable[[Any, str], Awaitable[None]]] = {
            "": self._kb_list,
            "list": self._kb_list,
            "search": self._kb_search,
            "article": self._kb_article,
            "ingest": self._kb_ingest,
        }
        handler = handlers.get(sub)
        if handler is None:
            self.app.notify(f"Unknown /kb subcommand: {sub}", severity="warning")
            return
        await handler(log, rest)

    async def _sdd_constitution(self, log: Any, rest: str) -> None:
        """``/sdd constitution`` — render the project constitution."""
        try:
            constitution = await self.app._client.get_constitution()
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "sdd constitution", exc)
            return
        if not constitution:
            await log.add_info("[yellow]No constitution defined yet.[/yellow]")
            return
        await log.add_info(self._render_constitution(constitution))

    async def _sdd_specs(self, log: Any, rest: str) -> None:
        """``/sdd specs`` — list the recorded specifications."""
        try:
            specs = await self.app._client.list_specs()
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "sdd specs", exc)
            return
        await log.add_info(self._render_specs(specs))

    async def _sdd_plans(self, log: Any, rest: str) -> None:
        """``/sdd plans`` — list the recorded plans."""
        try:
            plans = await self.app._client.list_plans()
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "sdd plans", exc)
            return
        await log.add_info(self._render_plans(plans))

    async def _sdd_tasks(self, log: Any, rest: str) -> None:
        """``/sdd tasks [plan_id]`` — list tasks, optionally scoped to a plan."""
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

    async def cmd_sdd(self, args: str) -> None:
        """Inspect Spec-Driven Development artifacts.

        Usage: /sdd [constitution | specs | plans | tasks [plan_id]]
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")
        handlers: dict[str, Callable[[Any, str], Awaitable[None]]] = {
            "constitution": self._sdd_constitution,
            "specs": self._sdd_specs,
            "plans": self._sdd_plans,
            "tasks": self._sdd_tasks,
        }
        handler = handlers.get(sub)
        if handler is None:
            self.app.notify(
                "Usage: /sdd [constitution | specs | plans | tasks [plan_id]]",
                severity="warning",
            )
            return
        await handler(log, rest)

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

    async def _write_codemap(self, log: Any, result: dict[str, Any]) -> None:
        """Render a codemap result's header plus its mermaid/markdown artifacts."""
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

    async def cmd_codemap(self, args: str) -> None:
        """Generate a codebase codemap. Usage: /codemap <prompt>"""
        log = self.app.query_one("Conversation")
        prompt = self._require_arg(args, "Usage: /codemap <prompt>")
        if prompt is None:
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

        await self._write_codemap(log, result)

    async def _resources_list(self, log: Any, rest: str) -> None:
        """``/resources list`` — render the callable-resource registry."""
        try:
            resources = await self.app._client.list_resources()
        except httpx.HTTPStatusError as exc:
            await self._write_http_error(log, "resources list", exc)
            return
        except Exception as exc:
            await log.add_info(f"[red]Error (resources list): {exc}[/red]")
            return
        await log.add_info(self._render_resources_table(resources))

    async def _parse_spawn_spec(self, log: Any, rest: str) -> dict[str, Any] | None:
        """Parse a ``/resources spawn`` JSON spec, or report why it is unusable."""
        if self._require_arg(rest, "Usage: /resources spawn <json_spec>") is None:
            return None
        try:
            spec = json.loads(rest)
        except json.JSONDecodeError as exc:
            self.app.notify(
                f"Invalid JSON for /resources spawn: {exc}", severity="error"
            )
            await log.add_info(f"[red]Invalid JSON for spawn spec:[/red] {exc}")
            return None
        if not isinstance(spec, dict):
            self.app.notify("Spawn spec must be a JSON object", severity="error")
            return None
        return spec

    async def _resources_spawn(self, log: Any, rest: str) -> None:
        """``/resources spawn <json_spec>`` — spawn a callable resource."""
        spec = await self._parse_spawn_spec(log, rest)
        if spec is None:
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

    async def cmd_resources(self, args: str) -> None:
        """List or spawn callable resources.

        Usage: /resources [list | spawn <json_spec>]
        """
        sub, rest = self._parse_subcommand(args)
        log = self.app.query_one("Conversation")
        handlers: dict[str, Callable[[Any, str], Awaitable[None]]] = {
            "": self._resources_list,
            "list": self._resources_list,
            "spawn": self._resources_spawn,
        }
        handler = handlers.get(sub)
        if handler is None:
            self.app.notify(f"Unknown /resources subcommand: {sub}", severity="warning")
            return
        await handler(log, rest)

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

    @staticmethod
    def _surface_error(result: dict[str, Any]) -> str | None:
        """Return a tool-level error string from a ``/graph/*`` payload, if any.

        The engine-surface tools degrade cleanly to ``{"error": "..."}`` at
        HTTP 200 rather than raising, so callers check this before rendering.
        """
        err = result.get("error") if isinstance(result, dict) else None
        return str(err) if err else None

    @staticmethod
    def _sparkline(values: list[float]) -> str:
        """Render a compact Unicode sparkline for a numeric series."""
        if not values:
            return ""
        blocks = "▁▂▃▄▅▆▇█"
        low = min(values)
        high = max(values)
        span = high - low
        if span <= 0:
            return blocks[0] * len(values)
        return "".join(
            blocks[min(len(blocks) - 1, int((v - low) / span * (len(blocks) - 1)))]
            for v in values
        )

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        """Best-effort float coercion for PromQL sample values."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _render_json_panel(self, title: str, result: dict[str, Any]) -> Panel:
        """Fallback renderer: pretty-print an unrecognized payload as JSON."""
        body = Syntax(
            json.dumps(result, indent=2, default=str),
            "json",
            word_wrap=True,
        )
        return Panel(body, title=title, border_style="cyan")

    @staticmethod
    def _row_columns(rows: list[Any]) -> list[str]:
        """Union of the keys across every mapping row, in stable order."""
        return sorted({k for row in rows if isinstance(row, dict) for k in row})

    @staticmethod
    def _dict_rows_table(title: str, rows: list[Any], columns: list[str]) -> Table:
        """Render mapping rows as a table with one column per known key."""
        table = Table(title=title, expand=True)
        for col in columns:
            table.add_column(col, overflow="fold")
        for row in rows[:50]:
            table.add_row(*[str(row.get(col, "")) for col in columns])
        return table

    @staticmethod
    def _scalar_rows_table(title: str, rows: list[Any]) -> Table:
        """Render non-mapping rows as a single-column table."""
        table = Table(title=title, expand=True)
        table.add_column("value")
        for row in rows[:50]:
            table.add_row(str(row))
        return table

    @staticmethod
    def _nl_query_header(result: dict[str, Any]) -> str:
        """Format the generated-query header for an ``nl_query`` payload."""
        query = result.get("query") or result.get("generated_query") or ""
        dialect = result.get("dialect", "")
        header = f"[bold blue]Generated query[/bold blue] ([dim]{dialect}[/dim])\n"
        return header + (
            f"[green]{query}[/green]" if query else "[dim](no query)[/dim]"
        )

    def _render_nl_query(self, result: dict[str, Any]) -> Any:
        """Render an ``nl_query`` payload: generated query + result rows."""
        err = self._surface_error(result)
        if err:
            return f"[red]NL query failed: {err}[/red]"
        header = self._nl_query_header(result)
        rows = result.get("rows") or result.get("results") or result.get("result") or []
        if not isinstance(rows, list) or not rows:
            return header + "\n[dim]No rows returned.[/dim]"
        columns = self._row_columns(rows)
        table = (
            self._dict_rows_table("Results", rows, columns)
            if columns
            else self._scalar_rows_table("Results", rows)
        )
        return Group(header, table)

    def _ask_data_parts(self, result: dict[str, Any]) -> list[Any]:
        """Collect the renderables for an ``ask_data`` payload, in order."""
        parts: list[Any] = []
        answer = result.get("answer") or ""
        if answer:
            parts.append(Panel(str(answer), title="Answer", border_style="green"))
        query = result.get("query") or result.get("generated_query") or ""
        if query:
            parts.append(Syntax(str(query), "sql", word_wrap=True))
        rows_table = self._ask_data_rows_table(result)
        if rows_table is not None:
            parts.append(rows_table)
        return parts

    def _ask_data_rows_table(self, result: dict[str, Any]) -> Table | None:
        """Build the ``ask_data`` rows table, or ``None`` when there is nothing."""
        rows = result.get("rows") or result.get("results") or []
        if not isinstance(rows, list) or not rows:
            return None
        columns = self._row_columns(rows)
        if not columns:
            return None
        return self._dict_rows_table("Rows", rows, columns)

    def _render_ask_data(self, result: dict[str, Any]) -> Any:
        """Render an ``ask_data`` payload: synthesized answer + query + rows."""
        err = self._surface_error(result)
        if err:
            return f"[red]Ask-data failed: {err}[/red]"
        parts = self._ask_data_parts(result)
        if not parts:
            return self._render_json_panel("Ask Data", result)
        return Group(*parts)

    @staticmethod
    def _promql_series(result: dict[str, Any]) -> Any:
        """Unwrap the sample series from a PromQL payload's nesting."""
        inner = result.get("result", result)
        if isinstance(inner, dict):
            return inner.get("result", inner.get("data", inner))
        return inner

    @staticmethod
    def _promql_label(entry: dict[str, Any]) -> str:
        """Build the display label for one PromQL series entry."""
        metric = entry.get("metric") or {}
        return str(
            metric.get("__name__")
            or ", ".join(f"{k}={v}" for k, v in metric.items())
            or "value"
        )

    def _promql_row(self, entry: dict[str, Any], action: str) -> list[str]:
        """Build the table cells for one PromQL series entry."""
        label = self._promql_label(entry)
        if action == "range":
            pairs = entry.get("values") or []
            nums = [n for _, raw in pairs if (n := self._coerce_float(raw)) is not None]
            last = f"{nums[-1]:g}" if nums else ""
            return [label, self._sparkline(nums), last]
        value = entry.get("value") or ["", ""]
        raw = value[1] if isinstance(value, list | tuple) and len(value) > 1 else value
        num = self._coerce_float(raw)
        return [label, f"{num:g}" if num is not None else str(raw)]

    def _render_promql(self, result: dict[str, Any], expr: str, action: str) -> Any:
        """Render a PromQL payload: a metric table plus a sparkline for ranges."""
        err = self._surface_error(result)
        if err:
            return f"[red]PromQL failed: {err}[/red]"
        series = self._promql_series(result)
        if not isinstance(series, list) or not series:
            return self._render_json_panel(f"PromQL: {expr}", result)
        table = Table(title=f"PromQL ({action}): {expr}", expand=True)
        table.add_column("Series", style="cyan", overflow="fold")
        if action == "range":
            table.add_column("Trend")
            table.add_column("Last", justify="right")
        else:
            table.add_column("Value", justify="right")
        for entry in series[:20]:
            if isinstance(entry, dict):
                table.add_row(*self._promql_row(entry, action))
            else:
                table.add_row(str(entry), "")
        return table

    @staticmethod
    def _trace_row(trace: dict[str, Any]) -> tuple[str, str, str, str]:
        """Build the table cells for one trace-search hit."""
        return (
            str(trace.get("trace_id") or trace.get("id", "")),
            str(trace.get("service") or trace.get("service_name", "")),
            str(trace.get("operation") or trace.get("name", "")),
            str(trace.get("duration_ms") or trace.get("duration") or ""),
        )

    def _render_traces(self, result: dict[str, Any]) -> Any:
        """Render a trace-search payload as a table."""
        err = self._surface_error(result)
        if err:
            return f"[red]Trace search failed: {err}[/red]"
        inner = result.get("result", result)
        traces = inner.get("traces", inner) if isinstance(inner, dict) else inner
        if not isinstance(traces, list) or not traces:
            return "[dim]No traces found.[/dim]"
        table = Table(title="Traces", expand=True)
        table.add_column("Trace ID", style="cyan", no_wrap=True)
        table.add_column("Service", style="magenta")
        table.add_column("Operation")
        table.add_column("Duration", justify="right")
        for trace in traces[:30]:
            if isinstance(trace, dict):
                table.add_row(*self._trace_row(trace))
        return table

    @staticmethod
    def _broker_item_row(item: Any) -> tuple[str, str]:
        """Build the table cells for one broker queue/exchange entry."""
        if not isinstance(item, dict):
            return str(item), ""
        name = item.get("name") or item.get("queue") or item.get("exchange", "")
        detail = ", ".join(f"{k}={v}" for k, v in item.items() if k not in ("name",))
        return str(name), detail

    def _render_broker_listing(self, inner: Any, action: str) -> Any:
        """Render a broker queue/exchange listing as a table."""
        items = inner
        if isinstance(inner, dict):
            items = (
                inner.get("queues") or inner.get("exchanges") or inner.get("result", [])
            )
        if not isinstance(items, list) or not items:
            return "[dim]No entries.[/dim]"
        table = Table(title=action.replace("_", " ").title(), expand=True)
        table.add_column("Name", style="cyan", overflow="fold")
        table.add_column("Detail")
        for item in items[:50]:
            table.add_row(*self._broker_item_row(item))
        return table

    def _render_broker(self, result: dict[str, Any], action: str) -> Any:
        """Render broker stats or a queue/exchange listing as a table."""
        err = self._surface_error(result)
        if err:
            return f"[red]Broker query failed: {err}[/red]"
        inner = result.get("result", result)
        if action in ("list_queues", "list_exchanges"):
            return self._render_broker_listing(inner, action)
        if not isinstance(inner, dict):
            return self._render_json_panel("Broker", result)
        table = Table(title="Broker Stats", expand=True)
        table.add_column("Metric", style="bold cyan")
        table.add_column("Value", justify="right")
        for key in sorted(inner):
            table.add_row(str(key), str(inner[key]))
        return table

    def _render_kvcache(self, result: dict[str, Any]) -> Any:
        """Render KV-cache occupancy and dedup counters as a table."""
        err = self._surface_error(result)
        if err:
            return f"[red]KV-cache query failed: {err}[/red]"
        inner = result.get("result", result)
        if not isinstance(inner, dict):
            return self._render_json_panel("KV-Cache", result)
        table = Table(title="KV-Cache Stats", expand=True)
        table.add_column("Metric", style="bold cyan")
        table.add_column("Value", justify="right")
        for key in sorted(inner):
            table.add_row(str(key), str(inner[key]))
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
    #  KG-Native Commands
    #  CONCEPT:TU-KG.compute.prompt-management-ahe-rollback / KG-003
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
            table = Table(
                title="Prompts (CONCEPT:TU-KG.compute.prompt-management-ahe-rollback)",
                expand=True,
            )
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
        table = Table(
            title="Agent Skills (CONCEPT:TU-KG.compute.granular-resource-queries)",
            expand=True,
        )
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
        table = Table(
            title="MCP Tools (CONCEPT:TU-KG.compute.granular-resource-queries)",
            expand=True,
        )
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
