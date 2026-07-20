"""Permissions screen for tool call approval.

Full-screen replacement for the modal ToolApprovalScreen, providing
a more professional UX with diff views, danger level indicators,
and clear approval keybindings.

Concept: AU-018 (Tool Permissions Screen)
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Static

from agent_terminal_ui.danger import DangerLevel, classify_command, get_danger_markup
from agent_terminal_ui.tui.tool_approval_screen import ToolApprovalResult

ToolDecision = Literal["accept", "deny"]


class PermissionItem(Vertical):
    """A single tool call permission request display."""

    DEFAULT_CSS = """
    PermissionItem {
        height: auto;
        margin: 0 0 1 0;
        padding: 1;
        border: solid $primary 30%;
        background: $surface;
    }

    PermissionItem.-accepted {
        border: solid $success;
    }

    PermissionItem.-rejected {
        border: solid $error;
    }

    PermissionItem .perm-header {
        height: 1;
        text-style: bold;
    }

    PermissionItem .perm-details {
        height: auto;
        margin: 0 0 0 2;
        color: $text-muted;
    }

    PermissionItem .perm-danger {
        height: 1;
        margin: 0 0 0 2;
    }

    PermissionItem .perm-buttons {
        height: 1;
        margin: 1 0 0 0;
        align: right middle;
    }

    PermissionItem .perm-buttons Button {
        min-width: 10;
        height: 1;
        margin: 0 1 0 0;
    }
    """

    def __init__(
        self,
        call_id: str,
        tool_name: str,
        tool_args: str = "",
        *,
        danger_level: DangerLevel = DangerLevel.UNKNOWN,
        details: str = "",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the permission item.

        Args:
            call_id: Unique tool call identifier.
            tool_name: Name of the tool.
            tool_args: Formatted arguments string.
            danger_level: Risk classification.
            details: Additional details about the tool call.
            name: Optional Textual name.
            id: Optional Textual id.
            classes: Optional Textual CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._call_id = call_id
        self._tool_name = tool_name
        self._tool_args = tool_args
        self._danger_level = danger_level
        self._details = details
        self._decision: ToolDecision | None = None

    @property
    def call_id(self) -> str:
        """The tool call identifier."""
        return self._call_id

    @property
    def decision(self) -> ToolDecision | None:
        """The user's decision for this tool call."""
        return self._decision

    def compose(self) -> ComposeResult:
        """Compose the permission item layout."""
        yield Static(
            f"🔧 {self._tool_name}",
            classes="perm-header",
            markup=True,
        )
        if self._tool_args:
            yield Static(
                self._tool_args,
                classes="perm-details",
                markup=False,
            )
        yield Static(
            get_danger_markup(self._danger_level),
            classes="perm-danger",
            markup=True,
        )
        if self._details:
            yield Static(
                self._details,
                classes="perm-details",
                markup=False,
            )
        with Horizontal(classes="perm-buttons"):
            yield Button(
                "✓ Allow",
                variant="success",
                id=f"allow-{self._call_id}",
            )
            yield Button(
                "✕ Reject",
                variant="error",
                id=f"reject-{self._call_id}",
            )

    def set_decision(self, decision: ToolDecision) -> None:
        """Set the decision for this item.

        Args:
            decision: 'accept' or 'deny'.
        """
        self._decision = decision
        self.set_class(decision == "accept", "-accepted")
        self.set_class(decision == "deny", "-rejected")


class PermissionsScreen(Screen[ToolApprovalResult]):
    """Full-screen permissions review for pending tool calls.

    Replaces the modal ToolApprovalScreen with a more comprehensive
    review experience including danger indicators and diff views.
    """

    CSS_PATH = "permissions.tcss"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("a", "allow_all", "Allow All", show=True),
        Binding("r", "reject_all", "Reject All", show=True),
        Binding("escape", "reject_all", "Cancel", show=True),
        Binding("enter", "allow_all", "Confirm", show=False),
    ]

    def __init__(
        self,
        pending_tools: dict[str, dict[str, Any]],
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the permissions screen.

        Args:
            pending_tools: Map of call IDs to tool call data.
            name: Optional Textual name.
            id: Optional Textual id.
            classes: Optional Textual CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._pending_tools = pending_tools
        self._items: dict[str, PermissionItem] = {}

    def compose(self) -> ComposeResult:
        """Compose the permissions screen layout."""
        with Vertical(id="permissions-container"):
            yield Static(
                "[$primary]Tool Approval Required[/$primary]",
                id="permissions-title",
                markup=True,
            )
            yield Static(
                "[dim]Review pending tool calls. Press [bold]a[/bold] to allow all, "
                "[bold]r[/bold] to reject all, or decide individually.[/dim]",
                id="permissions-help",
                markup=True,
            )

            with VerticalScroll(id="permissions-list"):
                from agent_terminal_ui.tui.tool_display._registry import get_formatter

                for call_id, data in self._pending_tools.items():
                    tool_name = data.get("name", "unknown_tool")

                    class MockEvent:
                        def __init__(self, d):
                            self.__dict__.update(d)

                        def __getattr__(self, n):
                            return self.__dict__.get(n)

                    formatter = get_formatter(tool_name)
                    args_str = formatter.format_call_header(MockEvent(data))

                    # Detect danger level for shell commands
                    danger = DangerLevel.UNKNOWN
                    if tool_name in (
                        "run_shell_with_diagnostics",
                        "bash",
                        "shell",
                        "execute_command",
                    ):
                        cmd = data.get("command", data.get("cmd", ""))
                        if isinstance(cmd, str):
                            danger = classify_command(cmd)

                    item = PermissionItem(
                        call_id,
                        tool_name,
                        args_str,
                        danger_level=danger,
                    )
                    self._items[call_id] = item
                    yield item

            with Horizontal(id="permissions-feedback"):
                yield Input(
                    placeholder="Optional feedback (rejecting all if provided)",
                    id="feedback-input",
                )

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle individual allow/reject button clicks."""
        btn_id = event.button.id
        if not btn_id:
            return

        if btn_id.startswith("allow-"):
            call_id = btn_id[6:]
            item = self._items.get(call_id)
            if item:
                item.set_decision("accept")
        elif btn_id.startswith("reject-"):
            call_id = btn_id[7:]
            item = self._items.get(call_id)
            if item:
                item.set_decision("deny")

        # Auto-close when all decided
        if all(item.decision is not None for item in self._items.values()):
            self._close_with_result()

    def action_allow_all(self) -> None:
        """Allow all pending tool calls."""
        for item in self._items.values():
            if item.decision is None:
                item.set_decision("accept")
        self._close_with_result()

    def action_reject_all(self) -> None:
        """Reject all pending tool calls."""
        for item in self._items.values():
            if item.decision is None:
                item.set_decision("deny")
        self._close_with_result()

    def _close_with_result(self) -> None:
        """Finalize decisions and dismiss."""
        decisions: dict[str, ToolDecision] = {}
        for call_id, item in self._items.items():
            decisions[call_id] = item.decision or "deny"

        feedback_input = self.query_one("#feedback-input", Input)
        feedback = feedback_input.value.strip() or None

        result = ToolApprovalResult(decisions=decisions, feedback=feedback)
        self.dismiss(result)
