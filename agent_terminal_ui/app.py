#!/usr/bin/python
# coding: utf-8
"""Agent Terminal User Interface (TUI) Application.

This module implements the primary Textual application for the agent terminal UI.
It handles user input, streams events from the agent server (using both
AG-UI and ACP protocols), manages tool execution flows, and provides
an interactive log for agent-to-user communication.
"""

import os
import time
import logging
from typing import Any, ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.message import Message
from textual.widgets import RichLog
from textual.containers import Horizontal

# Core client and command imports
from agent_terminal_ui.client import AgentClient, ACPClient
from agent_terminal_ui.commands import CommandProcessor

# TUI component imports
from agent_terminal_ui.tui.agent_timer import AgentTimer
from agent_terminal_ui.tui.css import AGENT_APP_CSS
from agent_terminal_ui.tui.formatters import BulletMarkdown, format_user_message
from agent_terminal_ui.tui.input_text_area import InputTextArea
from agent_terminal_ui.tui.status_line import MODE_COLORS, StatusLine
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
MODES: list[str] = list(MODE_COLORS.keys())


class AgentEventReceived(Message):
    """Event posted when a new message or tool call is received from the agent client."""

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
        Binding("ctrl+a", "select_all", "Select All", show=False, priority=True),
        Binding("shift+tab", "cycle_mode", "Cycle Mode", show=False, priority=True),
    ]

    def __init__(self) -> None:
        """Initialize the Agent application and its internal state."""
        super().__init__()
        self._last_ctrl_c: float = 0.0
        self._agent_mode: str = "ask"
        self._is_processing: bool = False
        self._processing_permissions: bool = False
        self._pending_tool_calls: dict[str, dict[str, Any]] = {}
        self._current_session_id: str | None = None

        # Initialize client instead of direct Agent
        server_url = os.getenv("AGENT_URL", "http://localhost:8000")
        self._client = AgentClient(base_url=server_url)
        self._acp_client: ACPClient | None = None
        self._enable_acp: bool = os.getenv("ENABLE_ACP", "false").lower() == "true"

        if self._enable_acp:
            self._acp_client = None  # Deferred
            self._acp_session_id: str | None = None

        self._cmd_processor = CommandProcessor(self)

    async def on_input_text_area_submitted(
        self, event: InputTextArea.Submitted
    ) -> None:
        """Handle the submission of text from the input area.

        Args:
            event: The submission event from the InputTextArea.

        """
        value = event.value.strip()
        if not value or self._is_processing:
            return

        # Check for commands first
        if await self._cmd_processor.process(value):
            self.query_one(InputTextArea).clear()
            return

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
            self._run_agent_turn(value, parts=parts, mode_id=self._agent_mode)

    async def _run_agent_turn(
        self,
        query: str,
        parts: list[dict[str, Any]] | None = None,
        mode_id: str = "ask",
    ) -> None:
        """Stream events from the agent server using the AG-UI protocol.

        Args:
            query: The user prompt to send.
            parts: Optional list of multi-modal parts.
            mode_id: The interactive mode requested.

        """
        async for event in self._client.stream(
            query, session_id=self._current_session_id, parts=parts, mode_id=mode_id
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

        # In ACP, we first send the message (RPC) then stream (now handled inside stream generator directly)
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
            return {"type": "turn_end"}
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
            log.write(f"[red]Error: {event.get('message')}[/red]")
            self._is_processing = False
            self.query_one(AgentTimer).stop()

        elif event_type == "turn_end" or (
            event_type == "text" and "[DONE]" in event.get("content", "")
        ):
            self._is_processing = False
            self.query_one(StatusLine).set_thinking(False)
            self.query_one(AgentTimer).stop()
            # Check for decisions needed (if any pending tool calls need approval)
            if any(
                tc.get("needs_approval") for tc in self._pending_tool_calls.values()
            ):
                self._show_tool_approval_modal()

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
        or performs a exit check.
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
            log.write("[red]Interrupted[/red]")
            return

        now = time.monotonic()
        if now - self._last_ctrl_c < DOUBLE_TAP_SECONDS:
            self.exit()
        else:
            self._last_ctrl_c = now
            text_area.clear()

    def action_select_all(self) -> None:
        """Perform a select-all action in the input text area."""
        self.query_one(InputTextArea).action_select_all()

    def action_cycle_mode(self) -> None:
        """Cycle through available agent interaction modes."""
        current_idx = MODES.index(self._agent_mode) if self._agent_mode in MODES else 0
        self._agent_mode = MODES[(current_idx + 1) % len(MODES)]

        display_mode = self._agent_mode if self._agent_mode != "ask" else "chat"
        self.query_one(StatusLine).set_mode(display_mode)

    def compose(self) -> ComposeResult:
        """Construct the visual layout of the application.

        Returns:
            A Textual ComposeResult containing the main layout components.

        """
        with Horizontal():
            yield RichLog(id="event-log", wrap=True, markup=True)
            yield WorkflowSidebar()
        yield AgentTimer()
        yield InputTextArea(id="input")
        yield StatusLine()

    def on_mount(self) -> None:
        """Handle the mount event when the application starts."""
        log = self.query_one("#event-log", RichLog)

        try:
            from pathlib import Path

            logo_path = Path(__file__).parent / "tui" / "logo.txt"
            logo_str = logo_path.read_text()
            logo = f"{logo_str}\n[bold white]Welcome to Agent Terminal UI[/bold white]\nType [cyan]/help[/cyan] to see available commands or [cyan]/plan[/cyan] to start planning.\n"
        except Exception:
            logo = "[bold white]Welcome to Agent Terminal UI[/bold white]\nType [cyan]/help[/cyan] to see available commands or [cyan]/plan[/cyan] to start planning.\n"

        log.write(logo)

        self.query_one(RichLog).can_focus = False
        self.query_one(StatusLine).can_focus = False
        self.query_one(AgentTimer).can_focus = False
        self.query_one(InputTextArea).focus()

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

        wrapped_pending = {cid: MockEvent(ev) for cid, ev in pending.items()}
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
    """The application entry point."""
    AgentApp().run()


if __name__ == "__main__":
    main()
