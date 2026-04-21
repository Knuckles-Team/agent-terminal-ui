#!/usr/bin/python
"""Modal screen for approving or rejecting pending tool calls.

This module provides the user interface for human-in-the-loop tool execution
permissions. It displays pending tools, allows individual or batch decisions,
and supports providing textual feedback for requested corrections.
"""

from dataclasses import dataclass, field
from typing import ClassVar, Literal

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from agent_terminal_ui.tui.tool_display._formatters import AgentToolCallEvent
from agent_terminal_ui.tui.tool_display._registry import get_formatter

ToolDecision = Literal["accept", "deny"]


@dataclass
class ToolApprovalResult:
    """Result returned when the approval modal is dismissed.

    Contains the map of user decisions and optional textual feedback.
    """

    decisions: dict[str, ToolDecision] = field(default_factory=dict)
    feedback: str | None = None


class ToolApprovalScreen(ModalScreen[ToolApprovalResult]):
    """Modal screen for approving or rejecting pending tool calls.

    Presents a focused dialog that dims the background and captures input
    to ensure the user reviews security-sensitive or destructive tool
    executions before they are finalized.
    """

    # Keyboard shortcuts for quick decisions
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "accept_all", "Accept All", show=False),
        Binding("y", "accept_all", "Accept All", show=False),
        Binding("n", "reject_all", "Reject All", show=False),
        Binding("escape", "reject_all", "Reject All", show=False),
    ]

    DEFAULT_CSS: str = """
    ToolApprovalScreen {
        align: left middle;
    }

    #approval-dialog {
        width: 80%;
        max-width: 60;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: tall $primary;
        padding: 0 2;
    }

    #approval-title {
        text-align: center;
        text-style: bold;
        border-bottom: solid $primary;
    }

    #tool-list {
        height: auto;
        max-height: 15;
    }

    #feedback-section {
        height: auto;
        border-top: solid $primary;
    }

    #feedback-input {
        width: 100%;
    }
    """

    def __init__(self, pending_tools: dict[str, AgentToolCallEvent]) -> None:
        """Initialize the approval screen with the set of pending tools.

        Args:
            pending_tools: A mapping of call IDs to tool call event objects.

        """
        super().__init__()
        self._pending_tools: dict[str, AgentToolCallEvent] = pending_tools
        self._decisions: dict[str, ToolDecision] = {}

    def compose(self) -> ComposeResult:
        """Construct the approval dialog layout.

        Returns:
            A Textual ComposeResult containing title, tool list, and feedback input.

        """
        with Vertical(id="approval-dialog"):
            yield Static("Tool Approval Required", id="approval-title")
            with VerticalScroll(id="tool-list"):
                for event in self._pending_tools.values():
                    yield ToolCallItem(event)
            with Vertical(id="feedback-section"):
                yield Input(
                    placeholder="Provide feedback (denies all).", id="feedback-input"
                )

    def on_mount(self) -> None:
        """Handle screen initialization. Shortcuts work without focusing input."""
        pass

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        """Handle submission of the feedback input.

        A non-empty feedback string triggers a global rejection, while
        an empty submission triggers a global acceptance.

        Args:
            _event: The focus event (not directly used).

        """
        feedback_input = self.query_one("#feedback-input", Input)
        if feedback_input.value.strip():
            self.action_reject_all()
        else:
            self.action_accept_all()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle individual Accept/Reject button clicks.

        Args:
            event: The Textual button press event.

        """
        button_id = event.button.id
        if button_id is None:
            return

        if button_id.startswith("accept-"):
            call_id = button_id[7:]  # Remove "accept-" prefix
            self._mark_decision(call_id, "accept")
        elif button_id.startswith("reject-"):
            call_id = button_id[7:]  # Remove "reject-" prefix
            self._mark_decision(call_id, "deny")

    def _mark_decision(self, call_id: str, decision: ToolDecision) -> None:
        """Record the decision for a single tool and update visual state.

        Args:
            call_id: The ID of the tool call.
            decision: Whether the call is 'accept' or 'deny'.

        """
        self._decisions[call_id] = decision

        # Find the item and update button visual states
        for item in self.query(ToolCallItem):
            if item.call_id == call_id:
                accept_btn = item.query_one(f"#accept-{call_id}", Button)
                reject_btn = item.query_one(f"#reject-{call_id}", Button)

                if decision == "accept":
                    accept_btn.add_class("selected")
                    accept_btn.remove_class("unselected")
                    reject_btn.remove_class("selected")
                    reject_btn.add_class("unselected")
                else:
                    accept_btn.remove_class("selected")
                    accept_btn.add_class("unselected")
                    reject_btn.add_class("selected")
                    reject_btn.remove_class("unselected")
                break

        # Auto-close when all decisions are made
        if len(self._decisions) == len(self._pending_tools):
            self._close_with_result()

    def action_accept_all(self) -> None:
        """Apply an 'accept' decision to all remaining undecided tools."""
        for call_id in self._pending_tools:
            if call_id not in self._decisions:
                self._decisions[call_id] = "accept"
        self._close_with_result()

    def action_reject_all(self) -> None:
        """Apply a 'deny' decision to all remaining undecided tools."""
        for call_id in self._pending_tools:
            if call_id not in self._decisions:
                self._decisions[call_id] = "deny"
        self._close_with_result()

    def _close_with_result(self) -> None:
        """Finalize decisions and dismiss the modal returning a Result object."""
        feedback_input = self.query_one("#feedback-input", Input)
        feedback = feedback_input.value.strip() or None

        result = ToolApprovalResult(decisions=self._decisions, feedback=feedback)
        self.dismiss(result)


class ToolCallItem(Horizontal):
    """Row component representing a single pendng tool call.

    Displays the tool call header and provides toggle buttons for approval.
    """

    DEFAULT_CSS: str = """
    ToolCallItem {
        height: 1;
        width: 100%;
        padding: 0 1;
        margin-bottom: 0;
    }

    ToolCallItem .tool-header {
        width: 1fr;
        height: 100%;
        content-align: left middle;
    }

    ToolCallItem .tool-btn {
        width: 5;
        min-width: 5;
        height: 1;
        min-height: 1;
        margin-left: 1;
        padding: 0;
        border: none;
    }

    ToolCallItem .tool-btn.selected {
        border: solid $primary;
    }

    ToolCallItem .tool-btn.unselected {
        opacity: 0.3;
    }
    """

    def __init__(self, event: AgentToolCallEvent) -> None:
        """Initialize the tool call item.

        Args:
            event: The tool call event to display.

        """
        super().__init__()
        self.event: AgentToolCallEvent = event
        self.call_id: str = event.call_id

    def compose(self) -> ComposeResult:
        """Construct the row layout with label and buttons.

        Returns:
            A Textual ComposeResult containing header label and Accept/Reject buttons.

        """
        formatter = get_formatter(self.event.name)
        header = formatter.format_call_header(self.event)
        yield Static(header, classes="tool-header")
        yield Button(
            "\u2713", variant="success", id=f"accept-{self.call_id}", classes="tool-btn"
        )
        yield Button(
            "\u2717", variant="error", id=f"reject-{self.call_id}", classes="tool-btn"
        )
