"""Main screen for the Agent Terminal UI.

Extracted from the monolithic app.py — this screen owns the conversation
layout, event handling, and sidebar. The app.py is simplified to delegate
all UI to this screen.

Concept: AU-018 (TUI Screen Architecture)
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, ClassVar

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, ProgressBar, RichLog, TabbedContent, TabPane

from agent_terminal_ui.tui.input_text_area import InputTextArea
from agent_terminal_ui.tui.status_line import StatusLine
from agent_terminal_ui.widgets.capability_sidebar import CapabilitySidebar
from agent_terminal_ui.widgets.conversation import Conversation
from agent_terminal_ui.widgets.graph_tree import GraphTree
from agent_terminal_ui.widgets.temporal_graph import TemporalGraph
from agent_terminal_ui.widgets.workflow import WorkflowSidebar

logger = logging.getLogger(__name__)


class _MockAgentToolCallEvent:
    """Adapts a plain event-data dict to attribute access, matching the
    `AgentToolCallEvent` protocol the tool_display formatters expect."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.__dict__.update(data)

    def __getattr__(self, name: str) -> Any:
        return self.__dict__.get(name)


class MainScreen(Screen):
    """Primary chat interface screen.

    Contains the conversation view, sidebar (workflow + graph), prompt input,
    and status line. Handles all agent event processing and display.
    """

    AUTO_FOCUS = "InputTextArea"
    CSS_PATH = "main.tcss"

    BINDINGS = [
        Binding("ctrl+b", "toggle_sidebar", "Sidebar", show=True),
        Binding("ctrl+l", "clear_conversation", "Clear", show=True),
        Binding("ctrl+v", "toggle_logs", "Logs", show=False),
    ]

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the main screen."""
        super().__init__(name=name, id=id, classes=classes)

    @property
    def agent_app(self):
        """Access the parent AgentApp."""
        return self.app

    def compose(self) -> ComposeResult:
        """Construct the main screen layout."""
        # Server log (hidden by default)
        yield RichLog(id="server-log", wrap=False, markup=True)

        # Main content: conversation + sidebar
        with Horizontal(id="main-content"):
            yield Conversation(id="conversation")
            with Vertical(id="sidebar"):
                with TabbedContent(initial="workflow-tab", id="sidebar-tabs"):
                    with TabPane("Workflow", id="workflow-tab"):
                        yield WorkflowSidebar()
                    with TabPane("Agent Graph", id="graph-tab"):
                        yield GraphTree("Swarm", id="agent-graph")
                    with TabPane("Temporal", id="temporal-tab"):
                        yield TemporalGraph(id="temporal-graph")
                    with TabPane("Capabilities", id="capabilities-tab"):
                        yield CapabilitySidebar(id="capability-sidebar")

        cmd_processor = getattr(self.agent_app, "_cmd_processor", None)
        input_commands = cmd_processor.commands if cmd_processor is not None else {}

        # Input area
        with Vertical(id="prompt-container"):
            yield ProgressBar(
                id="mcp-progress", total=100, show_eta=False, show_percentage=True
            )
            yield InputTextArea(
                id="input",
                commands=input_commands,
            )

        # Status line
        yield StatusLine()

        # Footer with key bindings
        yield Footer()

    async def on_mount(self) -> None:
        """Handle screen mount — display welcome and configure widgets."""
        conversation = self.query_one("#conversation", Conversation)

        # Display welcome banner
        try:
            logo_path = Path(__file__).parent.parent / "tui" / "logo.txt"
            logo_str = logo_path.read_text()
            logo = (
                f"{logo_str}\n"
                "[bold]Welcome to Agent Terminal UI[/bold]\n"
                "Type [$primary]/help[/$primary] to see available commands "
                "or [$primary]/plan[/$primary] to start planning.\n"
            )
        except Exception:
            logo = (
                "[bold]Welcome to Agent Terminal UI[/bold]\n"
                "Type [$primary]/help[/$primary] to see available commands "
                "or [$primary]/plan[/$primary] to start planning.\n"
            )

        await conversation.add_welcome(logo)

        # Configure non-focusable widgets
        self.query_one(StatusLine).can_focus = False
        self.query_one(InputTextArea).focus()

        # Limit RichLog max lines
        with contextlib.suppress(Exception):
            max_log_lines = self.agent_app.settings.get("max_log_lines", 1000)
            self.query_one("#server-log", RichLog).max_lines = max_log_lines

        # Hide progress bar initially
        pb = self.query_one("#mcp-progress", ProgressBar)
        pb.display = False

        # Start log tailing if log file is provided
        if log_file := os.getenv("AGENT_LOG_FILE"):
            self._tail_server_logs(log_file)

        # Register dynamic skill commands
        if hasattr(self.agent_app, "_cmd_processor"):

            async def register_skills():
                await self.agent_app._cmd_processor.register_skill_commands()
                input_area = self.query_one(InputTextArea)
                input_area._commands = getattr(
                    self.agent_app._cmd_processor, "commands", {}
                )

            self.run_worker(register_skills)

    # ── Event Handling ──

    async def handle_agent_event(self, event: dict[str, Any]) -> None:
        """Process a standardized agent event.

        Called by the parent AgentApp when events arrive from the protocol
        layer. Routes events to the appropriate conversation widget methods.

        Args:
            event: The event dictionary from the agent client.
        """
        conversation = self.query_one("#conversation", Conversation)
        event_type = event.get("type")

        handler = (
            self._EVENT_HANDLERS.get(event_type)
            if isinstance(event_type, str)
            else None
        )
        if handler is not None:
            await handler(self, conversation, event)
            return

        # NOTE: since "text" is dispatched above via _EVENT_HANDLERS, the
        # `event_type == "text" and "[DONE]" in ...` half of this condition
        # is unreachable in practice (an existing quirk, preserved as-is --
        # see the module's known-issues notes).
        if event_type == "turn_end" or (
            event_type == "text" and "[DONE]" in event.get("content", "")
        ):
            self._handle_turn_end_display(conversation, event)

    async def _handle_text_event(
        self, conversation: Conversation, event: dict[str, Any]
    ) -> None:
        content = event.get("content", "")
        agent_name = event.get("agent_name", "main")
        await conversation.add_agent_response(content, agent_name=agent_name)

    async def _handle_text_delta_event(
        self, conversation: Conversation, event: dict[str, Any]
    ) -> None:
        delta = event.get("content", "")
        agent_name = event.get("agent_name", "main")
        if conversation._current_response is None:
            await conversation.start_agent_response(agent_name=agent_name)
        await conversation.append_to_response(delta)

    async def _handle_tool_call_event(
        self, conversation: Conversation, event: dict[str, Any]
    ) -> None:
        data = event.get("data", {})
        call_id = data.get("call_id", "")
        tool_name = data.get("name", "unknown_tool")
        agent_name = data.get("agent_name", "main")
        needs_approval = data.get("needs_approval", False)
        status = "pending" if needs_approval else "in_progress"

        # Format tool args
        from agent_terminal_ui.tui.tool_display._registry import get_formatter

        formatter = get_formatter(tool_name)
        args_str = formatter.format_call_header(_MockAgentToolCallEvent(data))

        if tool_name != "todo_write":
            await conversation.add_tool_call(
                tool_name,
                args_str,
                status=status,
                agent_name=agent_name,
                call_id=call_id,
            )

        # If has output already
        if "output" in data:
            summary = formatter.format_output_summary(_MockAgentToolCallEvent(data))
            details = formatter.format_output_details(_MockAgentToolCallEvent(data))
            await conversation.update_tool_call(
                call_id,
                status="completed",
                content=summary,
                details=details,
            )

    async def _handle_tool_output_event(
        self, conversation: Conversation, event: dict[str, Any]
    ) -> None:
        data = event.get("data", {})
        call_id = data.get("call_id", "")
        tool_name = data.get("name", "unknown_tool")

        from agent_terminal_ui.tui.tool_display._registry import get_formatter

        formatter = get_formatter(tool_name)
        summary = formatter.format_output_summary(_MockAgentToolCallEvent(data))
        details = formatter.format_output_details(_MockAgentToolCallEvent(data))

        status = "failed" if data.get("error") else "completed"
        await conversation.update_tool_call(
            call_id,
            status=status,
            content=summary,
            details=details,
        )

    async def _handle_usage_display_event(
        self, _conversation: Conversation, event: dict[str, Any]
    ) -> None:
        data = event.get("data", {})
        with contextlib.suppress(Exception):
            self.query_one(StatusLine).update_usage(data)

    async def _handle_sideband_event(
        self, _conversation: Conversation, event: dict[str, Any]
    ) -> None:
        data = event.get("data", {})
        node = data.get("node")
        if not node:
            inner = data.get("data", data)
            graph_event = inner.get("event", "")
            if graph_event == "specialist_enter":
                node = inner.get("agent", inner.get("node_id"))
            elif graph_event == "specialist_exit":
                node = inner.get("agent", inner.get("node_id"))
                if node:
                    with contextlib.suppress(Exception):
                        self.query_one(WorkflowSidebar).update_state(
                            node, status="completed"
                        )
                    return
            elif graph_event in ("routing_started", "routing_completed"):
                node = "router"
            elif graph_event == "verification_result":
                node = "verifier"
        if node:
            with contextlib.suppress(Exception):
                self.query_one(WorkflowSidebar).update_state(node)

    async def _handle_error_display_event(
        self, conversation: Conversation, event: dict[str, Any]
    ) -> None:
        error_message = event.get("message", "An unknown error occurred")
        await conversation.add_error(error_message)

    #: Dispatch table for `handle_agent_event`, keyed by `event["type"]`.
    #: "turn_end" (and the text+"[DONE]" case) is handled separately below
    #: since it isn't a simple one-shot per-type handler.
    _EVENT_HANDLERS: ClassVar[
        dict[str, Callable[[MainScreen, Conversation, dict[str, Any]], Awaitable[None]]]
    ] = {
        "text": _handle_text_event,
        "text_delta": _handle_text_delta_event,
        "tool_call": _handle_tool_call_event,
        "tool_output": _handle_tool_output_event,
        "usage": _handle_usage_display_event,
        "sideband": _handle_sideband_event,
        "error": _handle_error_display_event,
    }

    def _handle_turn_end_display(
        self, conversation: Conversation, event: dict[str, Any]
    ) -> None:
        conversation.finish_agent_response()
        conversation.stop_thinking()
        if "usage" in event:
            with contextlib.suppress(Exception):
                self.query_one(StatusLine).update_usage(event["usage"])

    def start_processing(self) -> None:
        """Show thinking indicators."""
        conversation = self.query_one("#conversation", Conversation)
        conversation.start_thinking("Processing")
        with contextlib.suppress(Exception):
            self.query_one(StatusLine).set_thinking(True)

    def stop_processing(self) -> None:
        """Hide thinking indicators."""
        conversation = self.query_one("#conversation", Conversation)
        conversation.stop_thinking()
        with contextlib.suppress(Exception):
            self.query_one(StatusLine).set_thinking(False)

    async def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation.

        Args:
            content: The user message text.
        """
        conversation = self.query_one("#conversation", Conversation)
        await conversation.add_user_message(content)

    # ── Actions ──

    def action_toggle_sidebar(self) -> None:
        """Toggle sidebar visibility."""
        sidebar = self.query_one("#sidebar", Vertical)
        sidebar.display = not sidebar.display
        if sidebar.display:
            sidebar.focus()
        else:
            self.query_one(InputTextArea).focus()

    async def action_clear_conversation(self) -> None:
        """Clear the conversation."""
        conversation = self.query_one("#conversation", Conversation)
        await conversation.clear_conversation()
        self.notify("Conversation cleared", severity="information")

    def action_toggle_logs(self) -> None:
        """Toggle server log visibility."""
        log = self.query_one("#server-log", RichLog)
        log.display = not log.display

    def on_capability_sidebar_capability_selected(
        self, event: CapabilitySidebar.CapabilitySelected
    ) -> None:
        """Open a sidebar selection in the full schema-driven palette."""
        opener = getattr(self.agent_app, "open_capability_palette", None)
        if callable(opener):
            opener(capability_id=event.capability_id)

    # ── Log Tailing ──

    @work(exclusive=True)
    async def _tail_server_logs(self, log_file: str) -> None:
        """Background worker to tail the server log file."""
        import asyncio

        try:
            with open(log_file) as f:
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if not line:
                        await asyncio.sleep(0.1)
                        continue
                    self._write_server_log(line.strip())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._write_server_log(f"Log error: {e}")

    def _write_server_log(self, text: str) -> None:
        """Write a line to the server log widget."""
        import re

        with contextlib.suppress(Exception):
            self.query_one("#server-log", RichLog).write(text)

            # Check for MCP initialization progress
            # Example log: INFO -   [10/32] gitlab-api: 15 tools (7.1s)
            match = re.search(r"\[(\d+)/(\d+)\]", text)
            if match:
                current = int(match.group(1))
                total = int(match.group(2))
                try:
                    pb = self.query_one("#mcp-progress", ProgressBar)
                    pb.update(total=total, progress=current)
                    if not pb.display and current < total:
                        pb.display = True
                    if current >= total:
                        # Hide after a brief delay
                        def hide_pb():
                            pb.display = False

                        self.set_timer(1.0, hide_pb)
                except Exception:
                    pass  # nosec B110
