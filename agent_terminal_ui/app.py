import os
import time
from typing import Any, ClassVar

from agent_tui.client import AgentClient, ACPHttpClient
from agent_tui.commands import CommandProcessor
from agent_tui.tui.agent_timer import AgentTimer
from agent_tui.tui.css import AGENT_APP_CSS
from agent_tui.tui.formatters import BulletMarkdown, format_user_message
from agent_tui.tui.input_text_area import InputTextArea
from agent_tui.tui.status_line import MODE_COLORS, StatusLine
from agent_tui.tui.tool_approval_screen import ToolApprovalResult, ToolApprovalScreen
from agent_tui.tui.tool_display._registry import get_formatter
from agent_tui.tui.tool_display._widget import ToolCallDisplay, ToolOutputDisplay
from agent_tui.widgets.workflow import WorkflowSidebar
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.message import Message
from textual.widgets import RichLog

DOUBLE_TAP_SECONDS = 0.25
MODES = list(MODE_COLORS.keys())


class AgentEventReceived(Message):
    """Posted when an event is received from the agent client."""

    def __init__(self, event: dict[str, Any]) -> None:
        self.event = event
        super().__init__()


class AgentApp(App):
    CSS = AGENT_APP_CSS

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "interrupt", "Interrupt", show=False, priority=True),
        Binding("ctrl+a", "select_all", "Select All", show=False, priority=True),
        Binding("shift+tab", "cycle_mode", "Cycle Mode", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._last_ctrl_c: float = 0.0
        self._mode_index: int = 0
        self._is_processing: bool = False
        self._processing_permissions: bool = False
        self._pending_tool_calls: dict[str, dict[str, Any]] = {}
        self._current_session_id: str | None = None

        # Initialize client instead of direct Agent
        server_url = os.getenv("AGENT_URL", "http://localhost:8000")
        self._client = AgentClient(base_url=server_url)
        self._acp_client = None
        self._enable_acp = os.getenv("ENABLE_ACP", "false").lower() == "true"
        if self._enable_acp:
            acp_url = os.getenv("ACP_URL", "http://localhost:8001")
            self._acp_client = ACPHttpClient(base_url=acp_url)
            self._acp_session_id = None

        self._cmd_processor = CommandProcessor(self)

    async def on_input_text_area_submitted(
        self, event: InputTextArea.Submitted
    ) -> None:
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

        # Start agent turn via client
        self._is_processing = True
        self.query_one(StatusLine).set_thinking(True)
        if self._enable_acp:
            self._run_acp_turn(value)
        else:
            self._run_agent_turn(value)

    async def _run_agent_turn(self, query: str) -> None:
        """Stream events from the agent server (AG-UI)."""
        async for event in self._client.stream(
            query, session_id=self._current_session_id
        ):
            self.post_message(AgentEventReceived(event))

    @work(exclusive=True)
    async def _run_acp_turn(self, query: str) -> None:
        """Stream events from the ACP server."""
        if not self._acp_session_id:
            self._acp_session_id = await self._acp_client.create_session()

        # In ACP, we first send the message (RPC) then stream
        await self._acp_client.send_rpc(
            self._acp_session_id, method="prompt", params={"text": query}
        )

        async for event in self._acp_client.stream(self._acp_session_id):
            # Map ACP events to TUI events
            # ACP schema: {type: "text-delta", delta: "..."} etc.
            tui_event = self._map_acp_event(event)
            if tui_event:
                self.post_message(AgentEventReceived(tui_event))

    def _map_acp_event(self, acp_event: dict[str, Any]) -> dict[str, Any] | None:
        """Translates ACP protocol events to internal TUI event format."""
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
        """Handle events received from the agent client."""
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
            if "node" in data:
                node = data["node"]
                try:
                    self.query_one(WorkflowSidebar).update_state(node)
                except Exception:
                    pass

        elif event_type == "error":
            log.write(f"[red]Error: {event.get('message')}[/red]")
            self._is_processing = False
            self.query_one(AgentTimer).stop()

        elif event_type == "turn_end":
            self._is_processing = False
            self.query_one(StatusLine).set_thinking(False)
            self.query_one(AgentTimer).stop()
            # Check for decisions needed (if any pending tool calls need approval)
            if any(
                tc.get("needs_approval") for tc in self._pending_tool_calls.values()
            ):
                self._show_tool_approval_modal()

    def _handle_tool_call(self, data: dict[str, Any], log: RichLog) -> None:
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
            def __init__(self, d):
                self.__dict__.update(d)

            def __getattr__(self, name):
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
        call_id = data.get("call_id")
        call_data = self._pending_tool_calls.pop(call_id, None)

        name = data.get("name", "unknown_tool")
        agent_name = data.get("agent_name", "agent")

        formatter = get_formatter(name)

        class MockEvent:
            def __init__(self, d):
                self.__dict__.update(d)

            def __getattr__(self, name):
                return self.__dict__.get(name)

        header = (
            formatter.format_call_header(MockEvent(call_data)) if call_data else name
        )
        summary = formatter.format_output_summary(MockEvent(data))
        details = formatter.format_output_details(MockEvent(data))
        log.write(ToolOutputDisplay(header, summary, details, agent_name=agent_name))

    def action_interrupt(self) -> None:
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
        self.query_one(InputTextArea).action_select_all()

    def action_cycle_mode(self) -> None:
        self._mode_index = (self._mode_index + 1) % len(MODES)
        self.query_one(StatusLine).set_mode(MODES[self._mode_index])

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal

        with Horizontal():
            yield RichLog(id="event-log", wrap=True, markup=True)
            yield WorkflowSidebar()
        yield AgentTimer()
        yield InputTextArea(id="input")
        yield StatusLine()

    def on_mount(self) -> None:
        self.query_one(RichLog).can_focus = False
        self.query_one(StatusLine).can_focus = False
        self.query_one(AgentTimer).can_focus = False
        self.query_one(InputTextArea).focus()

    def _show_tool_approval_modal(self) -> None:
        pending = {
            cid: event
            for cid, event in self._pending_tool_calls.items()
            if event.get("needs_approval")
        }
        if not pending:
            return

        # We need to wrap dictionaries into MockEvent for the screen if it expects objects
        class MockEvent:
            def __init__(self, d):
                self.__dict__.update(d)

            def __getattr__(self, name):
                return self.__dict__.get(name)

        wrapped_pending = {cid: MockEvent(ev) for cid, ev in pending.items()}
        self.push_screen(
            ToolApprovalScreen(wrapped_pending), self._handle_tool_approval_result
        )

    def _handle_tool_approval_result(self, result: ToolApprovalResult | None) -> None:
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
        async for event in self._client.send_decision(decisions, feedback):
            self.post_message(AgentEventReceived(event))
        self._processing_permissions = False
        # If no turn_end event is caught in the stream, ensure we reset here
        if not self._is_processing:
            self.query_one(StatusLine).set_thinking(False)

    @work(exclusive=True)
    async def _resume_session(self, chat_id: str | None) -> None:
        """Fetch and display a past chat session."""
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
                # Handle assistant messages (could be text or tool calls)
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
            elif role == "tool":
                # Optional: log that a tool was run
                pass


def main() -> None:
    AgentApp().run()


if __name__ == "__main__":
    main()
