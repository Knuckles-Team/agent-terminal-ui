"""Modal screen for approving or rejecting pending tool calls.

This screen is displayed when the agent has tool calls that require user approval.
It shows all pending tools with individual Accept/Reject buttons.
Keyboard: Y accepts all, N/Esc rejects all, Enter accepts (no feedback) or rejects (with feedback).

Widget hierarchy:
    ToolApprovalScreen (ModalScreen - centers content, dims background)
    +-- #approval-dialog (Vertical - the visible dialog box)
        +-- #approval-title (Static - "Tool Approval Required")
        +-- #tool-list (VerticalScroll - scrollable list of tools)
        |   +-- ToolCallItem (one per pending tool)
        |       +-- .tool-header (Static - tool name and args)
        |       +-- Accept button
        |       +-- Reject button
        +-- #feedback-section (Vertical)
            +-- #feedback-input (Input)
"""

from dataclasses import dataclass, field
from typing import ClassVar, Literal

from agent_core._types import AgentToolCallEvent
from agent_tui.tui.tool_display._registry import get_formatter
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

ToolDecision = Literal["accept", "deny"]


@dataclass
class ToolApprovalResult:
    """Result returned when the approval modal is dismissed."""

    decisions: dict[str, ToolDecision] = field(default_factory=dict)
    feedback: str | None = None


class ToolApprovalScreen(ModalScreen[ToolApprovalResult]):
    """Modal screen for approving or rejecting pending tool calls.

    ModalScreen automatically:
    - Dims the background app
    - Centers content
    - Captures all keyboard input (prevents interaction with main app)
    - Returns a typed result via dismiss()
    """

    # Keyboard shortcuts for quick decisions
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "accept_all", "Accept All", show=False),
        Binding("y", "accept_all", "Accept All", show=False),
        Binding("n", "reject_all", "Reject All", show=False),
        Binding("escape", "reject_all", "Reject All", show=False),
    ]

    DEFAULT_CSS = """
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
        super().__init__()
        self._pending_tools = pending_tools
        self._decisions: dict[str, ToolDecision] = {}

    def compose(self) -> ComposeResult:
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
        # Don't focus feedback input by default so Y/N shortcuts work immediately
        pass

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        """Handle Enter in feedback input.

        If feedback is provided, reject all (user is giving correction).
        If no feedback, accept all (user is confirming).
        """
        feedback_input = self.query_one("#feedback-input", Input)
        if feedback_input.value.strip():
            self.action_reject_all()
        else:
            self.action_accept_all()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Route button presses to appropriate handlers based on button ID."""
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
        """Mark a single tool call decision.

        Updates button visual state to show which option is selected.
        Decisions can be changed by clicking the other button.
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
        """Accept all undecided tools and close the modal."""
        for call_id in self._pending_tools:
            if call_id not in self._decisions:
                self._decisions[call_id] = "accept"
        self._close_with_result()

    def action_reject_all(self) -> None:
        """Reject all undecided tools and close the modal."""
        for call_id in self._pending_tools:
            if call_id not in self._decisions:
                self._decisions[call_id] = "deny"
        self._close_with_result()

    def _close_with_result(self) -> None:
        """Dismiss the modal with the collected decisions and feedback."""
        feedback_input = self.query_one("#feedback-input", Input)
        feedback = feedback_input.value.strip() or None

        result = ToolApprovalResult(decisions=self._decisions, feedback=feedback)
        self.dismiss(result)


class ToolCallItem(Horizontal):
    """Widget for a single tool call with Accept/Reject buttons in a row."""

    DEFAULT_CSS = """
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
        super().__init__()
        self.event = event
        self.call_id = event.call_id

    def compose(self) -> ComposeResult:
        formatter = get_formatter(self.event.name)
        header = formatter.format_call_header(self.event)
        yield Static(header, classes="tool-header")
        # Button IDs encode the call_id for routing in on_button_pressed
        yield Button(
            "\u2713", variant="success", id=f"accept-{self.call_id}", classes="tool-btn"
        )
        yield Button(
            "\u2717", variant="error", id=f"reject-{self.call_id}", classes="tool-btn"
        )
