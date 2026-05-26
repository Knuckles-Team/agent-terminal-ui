#!/usr/bin/python
"""Agent Terminal User Interface (TUI) Application.

This module implements the primary Textual application for the agent terminal UI.
It handles user input, streams events from the agent server (using both
AG-UI and ACP protocols), manages tool execution flows, and delegates
UI rendering to the MainScreen.

Architecture:
    AgentApp (App) — protocol/client orchestration, global state
    └─ MainScreen (Screen) — conversation layout, event display
       ├─ Conversation — structured message blocks
       ├─ Sidebar — workflow + graph tree
       ├─ Prompt/Input — user input with overlays
       └─ StatusLine — mode, model, tokens

Concept: AU-018 (TUI Application Architecture)
"""

import contextlib
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


from textual.app import App
from textual.binding import Binding, BindingType
from textual.message import Message

# Core client and command imports
from agent_terminal_ui.client import ACPClient, AgentClient
from agent_terminal_ui.commands import CommandProcessor

# Screen imports
from agent_terminal_ui.screens.main import MainScreen

# TUI component imports (still needed for some actions)
from agent_terminal_ui.tui.chat_modal import ChatModal
from agent_terminal_ui.tui.exit_confirm_screen import ExitConfirmScreen
from agent_terminal_ui.tui.input_text_area import InputTextArea
from agent_terminal_ui.tui.status_line import StatusLine
from agent_terminal_ui.tui.tool_approval_screen import (
    ToolApprovalResult,
    ToolApprovalScreen,
)
from agent_terminal_ui.widgets.graph_tree import GraphTree

# Backward compat: keep formatters importable

logger = logging.getLogger(__name__)

DOUBLE_TAP_SECONDS: float = 0.25
MODES: list[str] = ["ask", "plan", "code", "chat", "build"]


class AgentEventReceived(Message):
    """Event posted when a message or tool call is received from the client."""

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
    the remote agent server. Delegates all UI to MainScreen.

    Concept: AU-018 (TUI Application Architecture)
    """

    TITLE = "Agent Terminal UI"
    SUB_TITLE = "Powered by agent-utilities"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "interrupt", "Interrupt", show=False, priority=True),
        Binding("ctrl+d", "quit_session", "Exit", show=False, priority=True),
        Binding("ctrl+a", "select_all", "Select All", show=False, priority=True),
        Binding("shift+tab", "cycle_mode", "Cycle Mode", show=False, priority=True),
        Binding("ctrl+q", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+h", "show_help", "Help", show=True, priority=True),
        Binding("ctrl+u", "clear_input", "Clear Input", show=False, priority=True),
        Binding("ctrl+y", "restore_input", "Restore", show=False, priority=True),
        Binding("ctrl+g", "open_editor", "Editor", show=False, priority=True),
        Binding("ctrl+r", "reverse_search", "Search", show=False, priority=True),
        Binding("alt+p", "switch_model_picker", "Model", show=False, priority=True),
        Binding("alt+t", "toggle_thinking", "Thinking", show=False, priority=True),
        Binding("alt+o", "toggle_fast_mode", "Fast", show=False, priority=True),
        Binding("alt+d", "switch_dashboard", "Dashboard", show=True, priority=True),
        Binding("escape,escape", "rewind", "Rewind", show=False, priority=True),
    ]

    MODES = {
        "main": MainScreen,
        "agents": "agent_view",  # Lazy import — resolved in on_mount
    }
    DEFAULT_MODE = "main"

    def __init__(
        self,
        theme_name: str = "tokyo-night",
        initial_prompt: str | None = None,
        auto_approve: bool = False,
        start_bg: bool = False,
    ) -> None:
        """Initialize the Agent application and its internal state.

        Args:
            theme_name: The Textual built-in theme name (default: tokyo-night).
            initial_prompt: An optional prompt to execute immediately on startup.
            auto_approve: If True, bypass tool approval modals and auto-accept.
            start_bg: If True, start in Agent View (background mode).
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

        self.initial_prompt = initial_prompt
        self.auto_approve = auto_approve

        # Set built-in theme (tokyo-night = blue palette)
        self.theme = theme_name

        # Initialize client
        server_url = os.getenv("AGENT_URL", "http://localhost:8000")
        self._client = AgentClient(base_url=server_url)
        self._acp_client: ACPClient | None = None
        self._enable_acp: bool = os.getenv("ENABLE_ACP", "false").lower() == "true"

        if self._enable_acp:
            self._acp_client = None  # Deferred
            self._acp_session_id: str | None = None

        self._cmd_processor = CommandProcessor(self)
        self.workspace_files: list[str] = []

    @property
    def current_session_id(self) -> str | None:
        """The active agent session identifier, if any."""
        return self._current_session_id

    @property
    def agent_client(self) -> AgentClient:
        """The underlying agent client used for backend communication."""
        return self._client

    def _get_main_screen(self) -> MainScreen | None:
        """Get the MainScreen instance if available."""
        try:
            screen = self.screen
            if isinstance(screen, MainScreen):
                return screen
        except Exception:  # nosec B110
            pass
        return None

    def on_mount(self) -> None:
        """Handle application startup."""
        self._scan_workspace_files()
        if self.initial_prompt:
            # Enqueue the prompt and let the main screen process it once ready
            self.call_after_refresh(self._submit_prompt, self.initial_prompt)

    async def on_unmount(self) -> None:
        """Clean up resources on unmount."""
        if hasattr(self, "_client") and self._client is not None:
            try:
                await self._client.close()
            except Exception as e:
                logger.warning(f"Failed to close AgentClient connection pool: {e}")

        if hasattr(self, "_acp_client") and self._acp_client is not None:
            try:
                await self._acp_client.close()
            except Exception as e:
                logger.warning(f"Failed to close ACPClient connection pool: {e}")

    # ── Message Queue ──

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
            (r"^(.*?)(?:\s+(?:and|also|plus|then|after that)\s+)(.+)$", r"\1 and \2"),
            (r"^(.*?)(?:\s+;\s*)(.+)$", r"\1; \2"),
            (
                r"^(fix|add|remove|update|create|delete|implement|refactor)\s+(.+)$",
                None,
            ),
        ]

        for pattern, replacement in combination_patterns:
            if replacement:
                combined = f"{last_message} and {new_message}"
                if len(combined) < 500:
                    return combined
            else:
                new_match = re.match(pattern, new_message, re.IGNORECASE)
                last_match = re.match(pattern, last_message, re.IGNORECASE)
                if new_match and last_match:
                    action = new_match.group(1).lower()
                    if action == last_match.group(1).lower():
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

        # Display and process the queued message
        main_screen = self._get_main_screen()
        if main_screen:
            self.run_worker(main_screen.add_user_message(message))

        self._is_processing = True
        if main_screen:
            main_screen.start_processing()

        if self._enable_acp:
            self._run_acp_turn(message, mode_id=self._agent_mode)
        else:
            self._run_agent_turn(
                message,
                parts=parts,
                mode_id=self._agent_mode,
                model=self._current_model,
            )

    # ── Input Handling ──

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
                main_screen = self._get_main_screen()
                if main_screen:
                    conversation = main_screen.query_one(
                        "#conversation",
                        lazy_import(
                            "agent_terminal_ui.widgets.conversation", "Conversation"
                        ),
                    )
                    await conversation.add_info(f"[$primary]> {bash_cmd}[/$primary]")
                await self._submit_prompt(f"Execute this shell command: {bash_cmd}")
                return

        # If currently processing, add to queue
        if self._is_processing and self._queue_enabled:
            combined = self._try_combine_queries(value)
            if combined:
                self._user_message_queue[-1]["message"] = combined
                main_screen = self._get_main_screen()
                if main_screen:
                    conversation = main_screen.query_one(
                        "#conversation",
                        lazy_import(
                            "agent_terminal_ui.widgets.conversation", "Conversation"
                        ),
                    )
                    await conversation.add_info(
                        f"[dim italic]Combined queued message: "
                        f"{combined[:100]}...[/dim italic]"
                    )
            else:
                parts = []
                if hasattr(self, "_pending_parts") and self._pending_parts:
                    parts = self._pending_parts
                    parts.append({"text": value})
                    self._pending_parts = []

                self._add_to_queue(value, parts)
                main_screen = self._get_main_screen()
                if main_screen:
                    conversation = main_screen.query_one(
                        "#conversation",
                        lazy_import(
                            "agent_terminal_ui.widgets.conversation", "Conversation"
                        ),
                    )
                    await conversation.add_info(
                        f"[dim italic]Queued message ({len(self._user_message_queue)} "
                        f"pending): {value[:100]}...[/dim italic]"
                    )

            self.query_one(InputTextArea).clear()
            return

        # Normal processing
        main_screen = self._get_main_screen()
        if main_screen:
            await main_screen.add_user_message(value)
            main_screen.start_processing()

        self.query_one(InputTextArea).clear()

        # Collect parts if any
        parts = []
        if hasattr(self, "_pending_parts") and self._pending_parts:
            parts = self._pending_parts
            parts.append({"text": value})
            self._pending_parts = []

        # Start agent turn
        self._is_processing = True
        if self._enable_acp:
            self._run_acp_turn(value, mode_id=self._agent_mode)
        else:
            self._run_agent_turn(
                value, parts=parts, mode_id=self._agent_mode, model=self._current_model
            )

    async def _submit_prompt(self, prompt: str) -> None:
        """Helper to submit a prompt to the agent programmatically."""
        main_screen = self._get_main_screen()
        if main_screen:
            main_screen.start_processing()

        self._is_processing = True
        if self._enable_acp:
            self._run_acp_turn(prompt, mode_id=self._agent_mode)
        else:
            self._run_agent_turn(
                prompt, parts=[], mode_id=self._agent_mode, model=self._current_model
            )

    # ── Protocol Communication ──

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
            mode_id: The interactive mode requested.
        """
        if not self._acp_client:
            return

        if not hasattr(self, "_acp_session_id") or not self._acp_session_id:
            self._acp_session_id = await self._acp_client.create_session()

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
            return None
        elif etype == "tool-call":
            return {"type": "tool_call", "data": acp_event.get("call", {})}
        elif etype == "turn-end":
            return {"type": "turn_end", "usage": acp_event.get("usage")}
        elif etype == "usage":
            return {"type": "usage", "data": acp_event.get("usage")}
        return None

    # ── Event Routing ──

    async def on_agent_event_received(self, message: AgentEventReceived) -> None:
        """Handle standardized events — route to MainScreen for display.

        Args:
            message: The event message from the agent client.
        """
        event = message.event
        event_type = event.get("type")

        # Route to MainScreen for display
        main_screen = self._get_main_screen()
        if main_screen:
            await main_screen.handle_agent_event(event)

        # Handle state management in app
        if event_type == "tool_call":
            data = event.get("data", {})
            call_id = data.get("call_id")
            if call_id:
                self._pending_tool_calls[call_id] = data

        elif event_type == "usage":
            data = event.get("data", {})
            self._last_usage = data

        elif event_type == "turn_end" or (
            event_type == "text" and "[DONE]" in event.get("content", "")
        ):
            self._is_processing = False
            if main_screen:
                main_screen.stop_processing()

            if "usage" in event:
                self._last_usage = event["usage"]

            # Check for decisions needed
            if any(
                tc.get("needs_approval") for tc in self._pending_tool_calls.values()
            ):
                self._show_tool_approval_modal()
            else:
                if self._user_message_queue:
                    self._process_queue()

        elif event_type == "error":
            self._is_processing = False
            if main_screen:
                main_screen.stop_processing()

    # ── Tool Approval ──

    def _show_tool_approval_modal(self) -> None:
        """Display a modal screen for approving pending tool calls."""
        pending = {
            cid: event
            for cid, event in self._pending_tool_calls.items()
            if event.get("needs_approval")
        }
        if not pending:
            return

        if self.auto_approve:
            from typing import Literal

            from agent_terminal_ui.tui.tool_approval_screen import ToolApprovalResult

            decisions: dict[str, Literal["accept", "deny"]] = {
                cid: "accept" for cid in pending.keys()
            }
            result = ToolApprovalResult(decisions=decisions, feedback=None)
            self._handle_tool_approval_result(result)
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

        main_screen = self._get_main_screen()

        for call_id, decision in result.decisions.items():
            tool_data = self._pending_tool_calls.get(call_id)
            if tool_data and main_screen:
                name = tool_data.get("name")
                status_text = (
                    "[$success]Accepted[/$success]"
                    if decision == "accept"
                    else "[$error]Rejected[/$error]"
                )
                self.run_worker(
                    main_screen.query_one(
                        "#conversation",
                        lazy_import(
                            "agent_terminal_ui.widgets.conversation", "Conversation"
                        ),
                    ).add_info(f"  {status_text}: {name}")
                )

        for call_id in result.decisions:
            self._pending_tool_calls.pop(call_id, None)

        self._processing_permissions = True
        self._is_processing = True
        if main_screen:
            main_screen.start_processing()
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
        if not self._is_processing:
            main_screen = self._get_main_screen()
            if main_screen:
                main_screen.stop_processing()

    # ── Session Management ──

    @work(exclusive=True)
    async def _resume_session(self, chat_id: str | None) -> None:
        """Fetch and display a past chat session from history.

        Args:
            chat_id: The unique identifier of the session to resume.
        """
        if not chat_id:
            return

        self._current_session_id = chat_id
        main_screen = self._get_main_screen()
        if not main_screen:
            return

        conversation = main_screen.query_one(
            "#conversation",
            lazy_import("agent_terminal_ui.widgets.conversation", "Conversation"),
        )
        await conversation.clear_conversation()
        await conversation.add_info(f"[$primary]Resuming session: {chat_id}[/$primary]")

        chat_data = await self._client.get_chat(chat_id)
        messages = chat_data.get("messages", [])

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "user":
                await conversation.add_user_message(content)
            elif role == "assistant":
                if isinstance(content, str):
                    await conversation.add_agent_response(content)
                elif isinstance(content, list):
                    for item in content:
                        text = item if isinstance(item, str) else item.get("text", "")
                        if text:
                            await conversation.add_agent_response(text)

    # ── Actions ──

    def action_interrupt(self) -> None:
        """Handle the interrupt action (Ctrl+C)."""
        try:
            text_area = self.query_one(InputTextArea)
            if not text_area.selection.is_empty:
                text_area.action_copy()
                return
        except Exception:  # nosec B110
            pass

        if self._is_processing:
            self.workers.cancel_all()
            self._is_processing = False
            main_screen = self._get_main_screen()
            if main_screen:
                main_screen.stop_processing()
                self.run_worker(
                    main_screen.query_one(
                        "#conversation",
                        lazy_import(
                            "agent_terminal_ui.widgets.conversation", "Conversation"
                        ),
                    ).add_info("[$warning]Operation interrupted by user[/$warning]")
                )
            return

        self.action_quit_session()

    def action_quit_session(self) -> None:
        """Handle the exit session action (Ctrl+D)."""

        def on_confirm(result: bool) -> None:
            if result:
                try:
                    self.exit()
                except Exception as e:
                    logger.error(f"Error during exit: {e}")

        self.push_screen(ExitConfirmScreen(callback=on_confirm))

    def action_select_all(self) -> None:
        """Perform a select-all action in the input text area."""
        with contextlib.suppress(Exception):
            self.query_one(InputTextArea).action_select_all()

    def action_cycle_mode(self) -> None:
        """Cycle through available agent interaction modes."""
        current_idx = MODES.index(self._agent_mode) if self._agent_mode in MODES else 0
        self._agent_mode = MODES[(current_idx + 1) % len(MODES)]

        display_mode = self._agent_mode if self._agent_mode != "ask" else "chat"
        with contextlib.suppress(Exception):
            self.query_one(StatusLine).set_mode(display_mode)

    def action_clear_input(self) -> None:
        """Clear the entire input buffer (Ctrl+U)."""
        with contextlib.suppress(Exception):
            text_area = self.query_one(InputTextArea)
            self._last_input_buffer = text_area.text
            text_area.clear()
            self.notify("Input cleared (Ctrl+Y to restore)", severity="information")

    def action_restore_input(self) -> None:
        """Restore the cleared input buffer (Ctrl+Y)."""
        if hasattr(self, "_last_input_buffer") and self._last_input_buffer:
            with contextlib.suppress(Exception):
                text_area = self.query_one(InputTextArea)
                text_area.text = self._last_input_buffer
                text_area.focus()
                self._last_input_buffer = ""
        else:
            self.notify("Nothing to restore", severity="warning")

    def action_show_help(self) -> None:
        """Show the help overlay — opens the command palette."""
        self.action_command_palette()

    def action_open_editor(self) -> None:
        """Open the current input in an external editor (Ctrl+G)."""
        self.notify("External editor support coming soon", severity="warning")

    def action_reverse_search(self) -> None:
        """Open reverse search history (Ctrl+R)."""
        self.run_worker(self._cmd_processor.cmd_history(""))

    def action_switch_model_picker(self) -> None:
        """Open the model selection picker (Alt+P)."""
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

    def action_switch_dashboard(self) -> None:
        """Switch to the service dashboard screen (Alt+D)."""
        try:
            from agent_terminal_ui.screens.dashboard import DashboardScreen

            self.push_screen(DashboardScreen())
        except ImportError:
            self.notify("Dashboard requires service-dashboard-core", severity="warning")

    def action_rewind(self) -> None:
        """Rewind conversation or code checkpoint (Esc Esc)."""
        self.notify("Rewind functionality coming soon", severity="warning")

    # ── Graph Tree Events ──

    def on_graph_tree_node_clicked(self, event: GraphTree.NodeClicked) -> None:
        """Handle when a node with messages is clicked in the Graph Tree."""
        messages = event.data.get("messages", [])
        title = event.data.get("title", "Subgraph Chat")
        self.push_screen(ChatModal(title=title, messages=messages))

    @work(exclusive=True, thread=True)
    def _scan_workspace_files(self) -> None:
        """Scan workspace files in the background."""
        import os

        files = []
        try:
            for root, dirs, filenames in os.walk("."):
                # Exclude common noisy directories
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".")
                    and d not in ("node_modules", "__pycache__", "venv", ".git")
                ]
                for f in filenames:
                    rel_path = os.path.relpath(os.path.join(root, f), ".")
                    if not rel_path.startswith("."):
                        files.append(rel_path)
                    # We can cap at a reasonable large limit (e.g. 5000)
                    if len(files) > 5000:
                        break
                if len(files) > 5000:
                    break
            self.workspace_files = sorted(files)
        except Exception as e:
            logger.warning(f"Failed to scan workspace files in background: {e}")


def lazy_import(module_path: str, class_name: str):
    """Lazily import a class to avoid circular imports.

    Args:
        module_path: The dotted module path.
        class_name: The class name to import.

    Returns:
        The imported class.
    """
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def main(
    initial_prompt: str | None = None,
    auto_approve: bool = False,
    start_bg: bool = False,
) -> None:
    """The application entry point."""
    theme_name = os.getenv("AGENT_THEME", "tokyo-night")
    AgentApp(
        theme_name=theme_name,
        initial_prompt=initial_prompt,
        auto_approve=auto_approve,
        start_bg=start_bg,
    ).run()


if __name__ == "__main__":
    main()
