#!/usr/bin/python
# coding: utf-8
"""Status line component for the terminal UI.

Displays session metadata such as the current interaction mode (plan/code),
active model information, token usage, and a thinking indicator.
"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

MODE_COLORS: dict[str, str] = {
    "plan": "#b48ead",
    "code": "#7aa2c7",
}

DEFAULT_MODE_COLOR: str = "#808080"


class StatusLine(Horizontal):
    """Bottom status line for the Agent Terminal UI.

    Maintains visual indicators for the current application state,
    including agent processing status and configured operational mode.
    """

    def compose(self) -> ComposeResult:
        """Construct the status line components.

        Returns:
            A Textual ComposeResult containing mode, model, and token widgets.

        """
        initial_color = MODE_COLORS.get("plan", DEFAULT_MODE_COLOR)
        yield Static(f"[{initial_color}]plan[/]", id="status-mode", markup=True)
        yield Static("", id="status-thinking", markup=True)
        yield Static("gpt-5.2", id="status-model")
        yield Static("12234 tokens", id="status-tokens")

    def set_mode(self, mode: str) -> None:
        """Update the displayed operational mode and its color.

        Args:
            mode: The name of the new mode (e.g., 'plan', 'code').

        """
        color = MODE_COLORS.get(mode, DEFAULT_MODE_COLOR)
        mode_widget = self.query_one("#status-mode", Static)
        mode_widget.update(f"[{color}]{mode}[/]")

    def set_thinking(self, is_thinking: bool) -> None:
        """Show or hide the thinking/processing indicator.

        Args:
            is_thinking: Whether the agent is currently processing a request.

        """
        thinking_widget = self.query_one("#status-thinking", Static)
        if is_thinking:
            thinking_widget.update("[bold cyan] Thinking...[/]")
        else:
            thinking_widget.update("")

    def update_usage(self, usage: dict) -> None:
        """Update the displayed token count and cost from usage metadata.

        Args:
            usage: A dictionary containing 'total_tokens' and 'estimated_cost_usd'.

        """
        tokens = usage.get("total_tokens", 0)
        cost = usage.get("estimated_cost_usd", 0.0)
        tokens_widget = self.query_one("#status-tokens", Static)
        tokens_widget.update(f"{tokens} tokens [dim](${cost:.4f})[/dim]")
