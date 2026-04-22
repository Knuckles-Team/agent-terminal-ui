#!/usr/bin/python
"""Agent Terminal User Interface (TUI) Application.

This module implements the primary Textual application for the agent terminal UI.
It handles user input, streams events from the agent server (using both
AG-UI and ACP protocols), manages tool execution flows, and provides
an interactive log for agent-to-user communication with modern theming support.
"""

import logging
import os
import re
import time
from typing import Any, ClassVar

try:
    from textual import work
except ImportError:
    # Fallback for older Textual versions
    def work(_exclusive=False, _group="default", _exit_on_error=True, _name=""):
        def decorator(func):
            return func

        return decorator


from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import RichLog

# Core client and command imports
from agent_terminal_ui.client import ACPClient, AgentClient
from agent_terminal_ui.commands import CommandProcessor

# TUI component imports
from agent_terminal_ui.tui.agent_timer import AgentTimer
from agent_terminal_ui.tui.css import AGENT_APP_CSS
from agent_terminal_ui.tui.exit_confirm_screen import ExitConfirmScreen
from agent_terminal_ui.tui.formatters import BulletMarkdown, format_user_message
from agent_terminal_ui.tui.input_text_area import InputTextArea
from agent_terminal_ui.tui.status_line import StatusLine
from agent_terminal_ui.tui.theme import (
    generate_css_from_theme,
    get_theme,
)
from agent_terminal_ui.tui.tool_approval_screen import (
    ToolApprovalResult,
    ToolApprovalScreen,
)
from agent_terminal_ui.tui.tool_display._registry import get_formatter
from agent_terminal_ui.tui.tool_display._widget import (
    ToolCallDisplay,
    ToolOutputDisplay,
)
from agent_terminal_ui.widgets.workflow import WorkflowSidebar

logger = logging.getLogger(__name__)

DOUBLE_TAP_SECONDS: float = 0.25
MODES: list[str] = ["ask", "plan", "code", "chat", "build"]


class AgentEventReceived(Message):
    """
    Event posted when a new message or tool call is received from the agent client.
    """

    def __init__(self, event: dict[str, Any]) -> None:
        """Initialize the event message with the raw event data.

        Args:
            event: The dictionary containing the event payload.

        """
        self.event = event
        super().__init__()


class AgentApp(App):
    """The main Textual application for the Agent Terminal UI.

    Responsible for orchestrating the lifecycle of an agent interaction session,
    managing UI state, and coordinating communication between the user and
    the remote agent server.
    """

    CSS: str = AGENT_APP_CSS

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "interrupt", "Interrupt", show=False, priority=True),
        Binding("ctrl+d", "quit_session", "Exit Session", show=False, priority=True),
        Binding("ctrl+a", "select_all", "Select All", show=False, priority=True),
        Binding("shift+tab", "cycle_mode", "Cycle Mode", show=False, priority=True),
        Binding("ctrl+q", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+h", "show_help", "Show Help", show=True, priority=True),
        Binding("ctrl+l", "clear_log", "Clear Log", show=True, priority=True),
        Binding("ctrl+o", "toggle_sidebar", "Toggle Sidebar", show=True, priority=True),
        Binding("ctrl+u", "clear_input", "Clear Input", show=False, priority=True),
        Binding("ctrl+y", "restore_input", "Restore Input", show=False, priority=True),
        Binding("ctrl+g", "open_editor", "Open in Editor", show=True, priority=True),
        Binding("ctrl+r", "reverse_search", "Reverse Search", show=True, priority=True),
        Binding(
            "ctrl+b", "show_background", "Background Tasks", show=True, priority=True
        ),
        Binding(
            "ctrl+t", "toggle_sidebar", "Toggle Task List", show=True, priority=True
        ),
        Binding(
            "ctrl+shift+t", "switch_theme", "Switch Theme", show=True, priority=True
        ),
        Binding(
            "alt+p", "switch_model_picker", "Switch Model", show=True, priority=True
        ),
        Binding(
            "alt+t", "toggle_thinking", "Toggle Thinking", show=True, priority=True
        ),
        Binding(
            "alt+o", "toggle_fast_mode", "Toggle Fast Mode", show=True, priority=True
        ),
        Binding("escape,escape", "rewind", "Rewind", show=True, priority=True),
    ]

    def __init__(self, theme_name: str = "modern_dark") -> None:
        """Initialize the Agent application and its internal state.

        Args:
            theme_name: The name of the theme to use (default: modern_dark).
        """
        super().__init__()
        self._last_ctrl_c: float = 0.0
        self._agent_mode: str = "ask"
        self._is_processing: bool = False
        self._processing_permissions: bool = False
        self._pending_tool_calls: dict[str, dict[str, Any]] = {}
        self._current_session_id: str | None = None
        self._pending_parts: list[dict[str, Any]] = []
        self._current_model: str | None = None

        # Message queue support
        self._user_message_queue: list[dict[str, Any]] = []
        self._queue_enabled: bool = True

        # Theme support
        self._current_theme = get_theme(theme_name)
        self._apply_theme()

        # Initialize client instead of direct Agent
        server_url = os.getenv("AGENT_URL", "http://localhost:8000")
        self._client = AgentClient(base_url=server_url)
        self._acp_client: ACPClient | None = None
        self._enable_acp: bool = os.getenv("ENABLE_ACP", "false").lower() == "true"

        if self._enable_acp:
            self._acp_client = None  # Deferred
            self._acp_session_id: str | None = None

        self._cmd_processor = CommandProcessor(self)

    def _add_to_queue(
        self, message: str, parts: list[dict[str, Any]] | None = None
    ) -> None:
        """Add a message to the processing queue.

        Args:
            message: The user message to queue.
            parts: Optional parts to include with the message.
        """
        queue_item = {
            "message": message,
            "parts": parts or [],
            "timestamp": time.time(),
        }
        self._user_message_queue.append(queue_item)
        logger.info(
            f"Added message to queue: {message[:50]}... "
            f"(Queue size: {len(self._user_message_queue)})"
        )

    def _try_combine_queries(
        self, new_message: str, parts: list[dict[str, Any]] | None = None
    ) -> str | None:
        """Try to combine the new message with the last queued message.

        Args:
            new_message: The new message to potentially combine.
            parts: Optional parts to include with the message.

        Returns:
            The combined message if combination succeeded, None otherwise.
        """
        if not self._user_message_queue:
            return None

        last_item = self._user_message_queue[-1]
        last_message = last_item["message"]

        # Combination patterns
        combination_patterns = [
            # Conjunctions that suggest combining
            (r"^(.*?)(?:\s+(?:and|also|plus|then|after that)\s+)(.+)$", r"\1 and \2"),
            # Sequential actions
            (r"^(.*?)(?:\s+;\s*)(.+)$", r"\1; \2"),
            # Similar structure (both starting with action verbs)
            (
                r"^(fix|add|remove|update|create|delete|implement|refactor)\s+(.+)$",
                None,
            ),
        ]

        for pattern, replacement in combination_patterns:
            # Try to combine if both messages match similar patterns
            if replacement:
                combined = f"{last_message} and {new_message}"
                # Check if the combination makes sense (not too long, similar structure)
                if len(combined) < 500:  # Reasonable length limit
                    return combined
            else:
                # Check if both messages start with the same action verb
                new_match = re.match(pattern, new_message, re.IGNORECASE)
                last_match = re.match(pattern, last_message, re.IGNORECASE)
                if new_match and last_match:
                    action = new_match.group(1).lower()
                    if action == last_match.group(1).lower():
                        # Same action, combine the targets
                        return (
                            f"{action} {last_match.group(2)} and {new_match.group(2)}"
                        )

        return None

    def _process_queue(self) -> None:
        """Process the next message in the queue if any."""
        if not self._user_message_queue:
            return

        next_item = self._user_message_queue.pop(0)
        message = next_item["message"]
        parts = next_item["parts"]

        logger.info(
            f"Processing queued message: {message[:50]}... "
            f"(Remaining: {len(self._user_message_queue)})"
        )

        # Display the queued message
        log = self.query_one("#event-log", RichLog)
        log.write(format_user_message(message))

        # Start processing the queued message
        self._is_processing = True
        self.query_one(AgentTimer).start()
        self.query_one(StatusLine).set_thinking(True)

        if self._enable_acp:
            self._run_acp_turn(message, mode_id=self._agent_mode)
        else:
            self._run_agent_turn(
                message,
                parts=parts,
                mode_id=self._agent_mode,
                model=self._current_model,
            )

    def _apply_theme(self) -> None:
        """Apply the current theme to the application."""
        # Generate theme-specific CSS
        theme_css = generate_css_from_theme(self._current_theme)
        # Combine with base CSS
        self.CSS = AGENT_APP_CSS + theme_css

    async def on_input_text_area_submitted(
        self, event: InputTextArea.Submitted
    ) -> None:
        """Handle the submission of text from the input area.

        Args:
            event: The submission event from the InputTextArea.

        """
        value = event.value.strip()
        if not value:
            return

        # Check for commands first
        if await self._cmd_processor.process(value):
            self.query_one(InputTextArea).clear()
            return

        # Handle direct bash execution via ! prefix
        if value.startswith("!"):
            bash_cmd = value[1:].strip()
            if bash_cmd:
                self.query_one(InputTextArea).clear()
                self.query_one("#event-log", RichLog).write(
                    f"[bold cyan]> {bash_cmd}[/bold cyan]"
                )
                # Use the run_shell_with_diagnostics tool logic (via agent turn)
                await self._submit_prompt(f"Execute this shell command: {bash_cmd}")
                return

        # If currently processing, add to queue
        if self._is_processing and self._queue_enabled:
            # Try to combine with the last queued message
            combined = self._try_combine_queries(value)
            if combined:
                # Replace the last queued message with the combined one
                self._user_message_queue[-1]["message"] = combined
                log = self.query_one("#event-log", RichLog)
                log.write(
                    f"[dim italic]Combined queued message: {combined[:100]}..."
                    "[/dim italic]"
                )
            else:
                # Add as a new queued message
                parts = []
                if hasattr(self, "_pending_parts") and self._pending_parts:
                    parts = self._pending_parts
                    parts.append({"text": value})
                    self._pending_parts = []

                self._add_to_queue(value, parts)
                log = self.query_one("#event-log", RichLog)
                log.write(
                    f"[dim italic]Queued message ({len(self._user_message_queue)} "
                    f"pending): {value[:100]}...[/dim italic]"
                )

            self.query_one(InputTextArea).clear()
            return

        # Normal processing when not busy
        self.query_one(AgentTimer).start()

        # Display user message
        log = self.query_one("#event-log", RichLog)
        log.write(format_user_message(value))
        self.query_one(InputTextArea).clear()

        # Collect parts if any
        parts = []
        if hasattr(self, "_pending_parts") and self._pending_parts:
            parts = self._pending_parts
            parts.append({"text": value})
            # To handle the pending parts clearing
            self._pending_parts = []

        # Start agent turn via client
        self._is_processing = True
        self.query_one(StatusLine).set_thinking(True)
        if self._enable_acp:
            self._run_acp_turn(value, mode_id=self._agent_mode)
        else:
            self._run_agent_turn(
                value, parts=parts, mode_id=self._agent_mode, model=self._current_model
            )

    async def _submit_prompt(self, prompt: str) -> None:
        """Helper to submit a prompt to the agent programmatically."""
        # This mimics the logic in on_input_text_area_submitted but for internal use
        self.query_one(AgentTimer).start()
        self._is_processing = True
        self.query_one(StatusLine).set_thinking(True)

        if self._enable_acp:
            self._run_acp_turn(prompt, mode_id=self._agent_mode)
        else:
            self._run_agent_turn(
                prompt, parts=[], mode_id=self._agent_mode, model=self._current_model
            )

    @work(exclusive=True)
    async def _run_agent_turn(
        self,
        query: str,
        parts: list[dict[str, Any]] | None = None,
        mode_id: str = "ask",
        model: str | None = None,
    ) -> None:
        """Stream events from the agent server using the AG-UI protocol.

        Args:
            query: The user prompt to send.
            parts: Optional list of multi-modal parts.
            mode_id: The interactive mode requested.
            model: Optional model identifier.

        """
        async for event in self._client.stream(
            query,
            session_id=self._current_session_id,
            parts=parts,
            mode_id=mode_id,
            model=model,
        ):
            self.post_message(AgentEventReceived(event))

    @work(exclusive=True)
    async def _run_acp_turn(self, query: str, mode_id: str = "ask") -> None:
        """Stream events from the ACP server.

        Args:
            query: The user prompt to send via the ACP protocol.
            mode_id: The interactive mode requested (e.g. 'plan' or 'ask').

        """
        if not self._acp_client:
            return

        if not hasattr(self, "_acp_session_id") or not self._acp_session_id:
            self._acp_session_id = await self._acp_client.create_session()

        # In ACP, we first send the message (RPC) then stream
        # (now handled inside stream generator directly)
        async for event in self._client.stream(
            query, session_id=self._acp_session_id, parts=None, mode_id=mode_id
        ):
            tui_event = self._map_acp_event(event)
            if tui_event:
                self.post_message(AgentEventReceived(tui_event))

    def _map_acp_event(self, acp_event: dict[str, Any]) -> dict[str, Any] | None:
        """Translate ACP protocol events to the internal TUI event format.

        Args:
            acp_event: The raw event received from the ACP protocol.

        Returns:
            A normalized dictionary compatible with the TUI event log, or None.

        """
        etype = acp_event.get("type")
        if etype == "text-delta":
            return {"type": "text", "content": acp_event.get("delta", "")}
        elif etype == "thinking":
            # ACP thinking events can be shown in status bar
            return None
        elif etype == "tool-call":
            return {"type": "tool_call", "data": acp_event.get("call", {})}
        elif etype == "turn-end":
            return {"type": "turn_end", "usage": acp_event.get("usage")}
        elif etype == "usage":
            return {"type": "usage", "data": acp_event.get("usage")}
        return None

    def on_agent_event_received(self, message: AgentEventReceived) -> None:
        """Handle standardized events received from the agent client.

        Args:
            message: The event message containing the payload from the agent.

        """
        event = message.event
        log = self.query_one("#event-log", RichLog)

        event_type = event.get("type")
        if event_type == "text":
            content = event.get("content", "")
            agent_name = event.get("agent_name", "agent")
            log.write(BulletMarkdown(content, agent_name=agent_name))

        elif event_type == "tool_call":
            data = event.get("data", {})
            self._handle_tool_call(data, log)

        elif event_type == "usage":
            data = event.get("data", {})
            self._last_usage = data
            # Update status line if it supports it
            try:
                self.query_one(StatusLine).update_usage(data)
            except Exception:
                pass

        elif event_type == "sideband":
            data = event.get("data", {})
            # Extract node information from various graph event formats
            node = data.get("node")
            if not node:
                # Try nested data-graph-event structure
                inner = data.get("data", data)
                graph_event = inner.get("event", "")
                if graph_event == "specialist_enter":
                    node = inner.get("agent", inner.get("node_id"))
                elif graph_event == "specialist_exit":
                    node = inner.get("agent", inner.get("node_id"))
                    if node:
                        try:
                            self.query_one(WorkflowSidebar).update_state(
                                node, status="completed"
                            )
                        except Exception:
                            pass
                        return
                elif graph_event in ("routing_started", "routing_completed"):
                    node = "router"
                elif graph_event == "verification_result":
                    node = "verifier"
            if node:
                try:
                    self.query_one(WorkflowSidebar).update_state(node)
                except Exception:
                    pass

        elif event_type == "error":
            error_message = event.get("message", "An unknown error occurred")
            log.write(f"[bold red]Error: {error_message}[/bold red]")
            self._is_processing = False
            self.query_one(AgentTimer).stop()

        elif event_type == "turn_end" or (
            event_type == "text" and "[DONE]" in event.get("content", "")
        ):
            self._is_processing = False
            self.query_one(StatusLine).set_thinking(False)
            self.query_one(AgentTimer).stop()

            # Update usage from turn_end if present
            if "usage" in event:
                self._last_usage = event["usage"]
                try:
                    self.query_one(StatusLine).update_usage(event["usage"])
                except Exception:
                    pass

            # Check for decisions needed (if any pending tool calls need approval)
            if any(
                tc.get("needs_approval") for tc in self._pending_tool_calls.values()
            ):
                self._show_tool_approval_modal()
            else:
                # Process next queued message if any
                if self._user_message_queue:
                    self._process_queue()

    def _handle_tool_call(self, data: dict[str, Any], log: RichLog) -> None:
        """Process and display a tool call event.

        Args:
            data: The tool call information.
            log: The event log to display the tool call in.

        """
        call_id = data.get("call_id")
        if not call_id:
            return

        self._pending_tool_calls[call_id] = data
        name = data.get("name", "unknown_tool")
        agent_name = data.get("agent_name", "agent")
        needs_approval = data.get("needs_approval", False)

        formatter = get_formatter(name)

        # Mocking an event-like object for the formatter
        class MockEvent:
            def __init__(self, d: dict[str, Any]) -> None:
                self.__dict__.update(d)

            def __getattr__(self, name: str) -> Any:
                return self.__dict__.get(name)

        header = formatter.format_call_header(MockEvent(data))

        if name != "todo_write":  # Hide internal tools
            log.write(
                ToolCallDisplay(header, pending=needs_approval, agent_name=agent_name)
            )

        # If it has output already (some tools execute immediately), handle it
        if "output" in data:
            self._handle_tool_output(data, log)

    def _handle_tool_output(self, data: dict[str, Any], log: RichLog) -> None:
        """Process and display the output of a tool call.

        Args:
            data: The tool execution result data.
            log: The event log to display the output in.

        """
        call_id = data.get("call_id")
        if not isinstance(call_id, str):
            return
        call_data = self._pending_tool_calls.pop(call_id, None)

        name = data.get("name", "unknown_tool")
        agent_name = data.get("agent_name", "agent")

        formatter = get_formatter(name)

        class MockEvent:
            def __init__(self, d: dict[str, Any]) -> None:
                self.__dict__.update(d)

            def __getattr__(self, name: str) -> Any:
                return self.__dict__.get(name)

        header = (
            formatter.format_call_header(MockEvent(call_data)) if call_data else name
        )
        summary = formatter.format_output_summary(MockEvent(data))
        details = formatter.format_output_details(MockEvent(data))
        log.write(ToolOutputDisplay(header, summary, details, agent_name=agent_name))

    def action_interrupt(self) -> None:
        """Handle the interrupt action (Ctrl+C).

        Clears selection if active, cancels pending work if processing,
        or shows exit confirmation dialog.
        """
        text_area = self.query_one(InputTextArea)
        if not text_area.selection.is_empty:
            text_area.action_copy()
            return

        if self._is_processing:
            self.workers.cancel_all()
            self._is_processing = False
            self.query_one(AgentTimer).hide()
            log = self.query_one("#event-log", RichLog)
            log.write("[bold yellow]Operation interrupted by user[/bold yellow]")
            return

        self.action_quit_session()

    def action_quit_session(self) -> None:
        """Handle the exit session action (Ctrl+D)."""

        # Show exit confirmation dialog
        def on_confirm(result: bool) -> None:
            """Handle the user's confirmation choice."""
            if result:
                try:
                    self.exit()
                except Exception as e:
                    # Log error but don't crash
                    import logging

                    logging.getLogger(__name__).error(f"Error during exit: {e}")

        self.push_screen(ExitConfirmScreen(callback=on_confirm))

    def action_clear_log(self) -> None:
        """Clear the event log (Ctrl+L)."""
        self.query_one("#event-log", RichLog).clear()
        self.refresh()
        self.notify("Log cleared", severity="information")

    def action_toggle_sidebar(self) -> None:
        """Toggle the visibility of the workflow sidebar (Ctrl+O, Ctrl+T)."""
        sidebar = self.query_one(WorkflowSidebar)
        sidebar.display = not sidebar.display
        if sidebar.display:
            sidebar.focus()
        else:
            self.query_one(InputTextArea).focus()

    def action_clear_input(self) -> None:
        """Clear the entire input buffer (Ctrl+U)."""
        text_area = self.query_one(InputTextArea)
        self._last_input_buffer = text_area.text
        text_area.clear()
        self.notify("Input cleared (Ctrl+Y to restore)", severity="information")

    def action_restore_input(self) -> None:
        """Restore the cleared input buffer (Ctrl+Y)."""
        if hasattr(self, "_last_input_buffer") and self._last_input_buffer:
            text_area = self.query_one(InputTextArea)
            text_area.text = self._last_input_buffer
            text_area.focus()
            self._last_input_buffer = ""
        else:
            self.notify("Nothing to restore", severity="warning")

    def action_open_editor(self) -> None:
        """Open the current input in an external editor (Ctrl+G)."""
        self.notify("External editor support not yet implemented", severity="warning")

    def action_reverse_search(self) -> None:
        """Open reverse search history (Ctrl+R)."""
        # For now, just open the history screen
        self._cmd_processor.cmd_history("")

    def action_show_background(self) -> None:
        """Show background running tasks (Ctrl+B)."""
        self.notify("Background tasks view not yet implemented", severity="warning")

    def action_switch_model_picker(self) -> None:
        """Open the model selection picker (Alt+P)."""
        # For now, just show current model in a notification
        current = getattr(self, "_current_model", "default")
        self.notify(
            f"Current model: {current or 'default'}. Use /model to change.",
            severity="information",
        )

    def action_toggle_thinking(self) -> None:
        """Toggle extended thinking mode (Alt+T)."""
        self._extended_thinking = not getattr(self, "_extended_thinking", False)
        status = "enabled" if self._extended_thinking else "disabled"
        self.notify(f"Extended thinking {status}", severity="information")

    def action_toggle_fast_mode(self) -> None:
        """Toggle fast mode (Alt+O)."""
        self._fast_mode = not getattr(self, "_fast_mode", False)
        status = "enabled" if self._fast_mode else "disabled"
        self.notify(f"Fast mode {status}", severity="information")

    def action_rewind(self) -> None:
        """Rewind conversation or code checkpoint (Esc Esc)."""
        self.notify("Rewind functionality not yet implemented", severity="warning")

    def action_select_all(self) -> None:
        """Perform a select-all action in the input text area."""
        self.query_one(InputTextArea).action_select_all()

    def action_cycle_mode(self) -> None:
        """Cycle through available agent interaction modes."""
        current_idx = MODES.index(self._agent_mode) if self._agent_mode in MODES else 0
        self._agent_mode = MODES[(current_idx + 1) % len(MODES)]

        display_mode = self._agent_mode if self._agent_mode != "ask" else "chat"
        self.query_one(StatusLine).set_mode(display_mode)

    def action_show_help(self) -> None:
        """Show the help overlay with keyboard shortcuts and commands."""
        from textual import events
        from textual.containers import Horizontal, Vertical
        from textual.widget import Widget
        from textual.widgets import Button, Label

        class HelpOverlay(Widget):
            """An overlay widget for displaying help information."""

            DEFAULT_CSS = """
            HelpOverlay {
                layer: help_overlay;
                align: center middle;
            }
            #help-dialog {
                width: 60;
                background: $surface;
                border: solid $border;
                padding: 2;
            }
            #help-title {
                text-align: center;
                padding: 1 0 2 0;
                text-style: bold;
                color: $primary;
            }
            #help-content {
                margin: 1 0;
            }
            #help-close {
                align: center middle;
                margin-top: 1;
            }
            #help-close Button {
                min-width: 12;
            }
            .help-section {
                margin: 1 0;
            }
            .help-section-title {
                text-style: bold;
                color: $primary;
                margin: 1 0 0 0;
            }
            .help-item {
                margin: 0 0 0 2;
            }
            .help-key {
                color: $success;
                text-style: bold;
            }
            """

            def __init__(self, on_close):
                self.on_close = on_close
                super().__init__()

            def compose(self):
                with Vertical(id="help-dialog"):
                    yield Label("Keyboard Shortcuts", id="help-title")

                    with Vertical(id="help-content"):
                        yield Label("Keyboard Shortcuts", classes="help-section-title")
                        yield Label(
                            "[help-key]Ctrl+C[/help-key] - Interrupt action",
                            classes="help-item",
                        )
                        yield Label(
                            "[help-key]Ctrl+A[/help-key] - Select all text",
                            classes="help-item",
                        )
                        yield Label(
                            "[help-key]Ctrl+Q[/help-key] - Quit application",
                            classes="help-item",
                        )
                        yield Label(
                            "[help-key]Ctrl+H[/help-key] - Show this help",
                            classes="help-item",
                        )
                        yield Label(
                            "[help-key]Ctrl+T[/help-key] - Switch theme",
                            classes="help-item",
                        )
                        yield Label(
                            "[help-key]Shift+Tab[/help-key] - Cycle mode",
                            classes="help-item",
                        )

                        yield Label("Slash Commands", classes="help-section-title")
                        yield Label(
                            "[help-key]/help[/help-key] - Show available commands",
                            classes="help-item",
                        )
                        yield Label(
                            "[help-key]/clear[/help-key] - Clear conversation",
                            classes="help-item",
                        )
                        yield Label(
                            "[help-key]/history[/help-key] - Browse chat history",
                            classes="help-item",
                        )
                        yield Label(
                            "[help-key]/mcp[/help-key] - Browse MCP servers",
                            classes="help-item",
                        )

                    with Horizontal(id="help-close"):
                        yield Button("Close", variant="primary", id="close-btn")

            def on_button_pressed(self, event: Button.Pressed) -> None:
                if event.button.id == "close-btn":
                    self.on_close()
                event.stop()

            def on_key(self, event: events.Key):
                if event.key == "escape":
                    self.on_close()
                    event.stop()
                    event.prevent_default()

        def on_close():
            self.query_one(HelpOverlay).remove()

        self.mount(HelpOverlay(on_close))

    def action_switch_theme(self) -> None:
        """Switch to the next available theme."""
        from agent_terminal_ui.tui.theme import list_themes

        themes = list_themes()
        current_theme = self._current_theme.name

        try:
            current_idx = themes.index(current_theme)
            next_idx = (current_idx + 1) % len(themes)
            next_theme = themes[next_idx]
            self.switch_theme(next_theme)
        except (ValueError, IndexError):
            # If current theme not found, switch to default
            self.switch_theme("modern_dark")

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    def switch_theme(self, theme_name: str) -> None:
        """Switch to a different theme.

        Args:
            theme_name: The name of the theme to switch to.
        """
        from agent_terminal_ui.tui.theme import AVAILABLE_THEMES

        if theme_name.lower() not in AVAILABLE_THEMES:
            self.notify(f"Unknown theme: {theme_name}", severity="error")
            return

        self._current_theme = get_theme(theme_name)
        self._apply_theme()

        # Update status line colors if needed
        try:
            status_line = self.query_one(StatusLine)
            status_line.set_mode(self._agent_mode)
        except Exception:
            pass

        self.notify(
            f"Switched to {self._current_theme.name} theme", severity="information"
        )

    def compose(self) -> ComposeResult:
        """Construct the visual layout of the application.

        Returns:
            A Textual ComposeResult containing the main layout components.

        """
        with Horizontal():
            yield RichLog(id="event-log", wrap=True, markup=True)
            yield WorkflowSidebar()
        yield AgentTimer()
        yield InputTextArea(id="input", commands=self._cmd_processor.commands)
        yield StatusLine()

    def on_mount(self) -> None:
        """Handle the mount event when the application starts."""
        log = self.query_one("#event-log", RichLog)

        try:
            from pathlib import Path

            logo_path = Path(__file__).parent / "tui" / "logo.txt"
            logo_str = logo_path.read_text()
            logo = (
                f"{logo_str}\n"
                "[bold white]Welcome to Agent Terminal UI[/bold white]\n"
                "Type [cyan]/help[/cyan] to see available commands "
                "or [cyan]/plan[/cyan] to start planning.\n"
            )
        except Exception:
            logo = (
                "[bold white]Welcome to Agent Terminal UI[/bold white]\n"
                "Type [cyan]/help[/cyan] to see available commands "
                "or [cyan]/plan[/cyan] to start planning.\n"
            )

        log.write(logo)

        self.query_one(RichLog).can_focus = False
        self.query_one(StatusLine).can_focus = False
        self.query_one(AgentTimer).can_focus = False
        self.query_one(InputTextArea).focus()

        # Register dynamic skill commands

        async def register_skills():
            await self._cmd_processor.register_skill_commands()
            # Update InputTextArea with new commands
            input_area = self.query_one(InputTextArea)
            input_area._commands = self._cmd_processor.commands

        self.run_worker(register_skills)

    def _show_tool_approval_modal(self) -> None:
        """Display a modal screen for approving pending tool calls."""
        pending = {
            cid: event
            for cid, event in self._pending_tool_calls.items()
            if event.get("needs_approval")
        }
        if not pending:
            return

        class MockEvent:
            def __init__(self, d: dict[str, Any]) -> None:
                self.__dict__.update(d)

            def __getattr__(self, name: str) -> Any:
                return self.__dict__.get(name)

        from typing import cast

        from agent_terminal_ui.tui.tool_display._formatters import AgentToolCallEvent

        wrapped_pending = {
            cid: cast(AgentToolCallEvent, MockEvent(ev)) for cid, ev in pending.items()
        }
        self.push_screen(
            ToolApprovalScreen(wrapped_pending), self._handle_tool_approval_result
        )

    def _handle_tool_approval_result(self, result: ToolApprovalResult | None) -> None:
        """Handle the result of a tool approval decision.

        Args:
            result: The user's decisions and feedback, or None if cancelled.

        """
        if result is None:
            return

        log = self.query_one("#event-log", RichLog)
        for call_id, decision in result.decisions.items():
            tool_data = self._pending_tool_calls.get(call_id)
            if tool_data:
                name = tool_data.get("name")
                status = (
                    "[green]Accepted[/green]"
                    if decision == "accept"
                    else "[red]Rejected[/red]"
                )
                log.write(f"  {status}: {name}")

        for call_id in result.decisions:
            self._pending_tool_calls.pop(call_id, None)

        self._processing_permissions = True
        self._is_processing = True
        self.query_one(StatusLine).set_thinking(True)
        self.query_one(AgentTimer).start()
        self._run_agent_turn_with_permissions(result.decisions, result.feedback)

    @work(exclusive=True)
    async def _run_agent_turn_with_permissions(
        self, decisions: dict[str, str], feedback: str | None
    ) -> None:
        """Resume an agent turn after user decisions are made.

        Args:
            decisions: Map of call IDs to 'accept' or 'reject'.
            feedback: Optional feedback provided by the user.

        """
        async for event in self._client.send_decision(decisions, feedback):
            self.post_message(AgentEventReceived(event))
        self._processing_permissions = False
        # Ensure we reset thinking state if the stream ends
        if not self._is_processing:
            self.query_one(StatusLine).set_thinking(False)

    @work(exclusive=True)
    async def _resume_session(self, chat_id: str | None) -> None:
        """Fetch and display a past chat session from history.

        Args:
            chat_id: The unique identifier of the session to resume.

        """
        if not chat_id:
            return

        self._current_session_id = chat_id
        log = self.query_one("#event-log", RichLog)
        log.clear()
        log.write(f"[bold blue]Resuming session: {chat_id}[/bold blue]\n")

        chat_data = await self._client.get_chat(chat_id)
        messages = chat_data.get("messages", [])

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "user":
                log.write(format_user_message(content))
            elif role == "assistant":
                if isinstance(content, str):
                    log.write(BulletMarkdown(content, agent_name="assistant"))
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, str):
                            log.write(BulletMarkdown(item, agent_name="assistant"))
                        elif isinstance(item, dict) and "text" in item:
                            log.write(
                                BulletMarkdown(item["text"], agent_name="assistant")
                            )


def main() -> None:
    """The application entry point with theme support."""
    # Get theme from environment variable or use default
    theme_name = os.getenv("AGENT_THEME", "modern_dark")
    AgentApp(theme_name=theme_name).run()


if __name__ == "__main__":
    main()
