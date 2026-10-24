#!/usr/bin/python
"""Status line component for the terminal UI.

Displays session metadata such as the current interaction mode,
active model information, token usage, and a thinking indicator.
Uses Textual design tokens for consistent theming.

Concept: AU-018 (TUI Status Line)
"""

import math

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class StatusLine(Horizontal):
    """Bottom status line for the Agent Terminal UI.

    Maintains visual indicators for the current application state,
    including agent processing status and configured operational mode,
    using Textual design tokens for theme consistency.
    """

    DEFAULT_CSS = """
    StatusLine {
        dock: bottom;
        height: auto;
        margin: 0;
        padding: 0;
        background: $surface;
        border-top: solid $primary 20%;
    }

    StatusLine Static {
        width: auto;
        padding: 0 1;
    }

    #status-mode {
        color: $primary;
        text-style: bold;
    }

    #status-model {
        max-width: 15%;
        height: 1;
        color: $text-muted;
    }

    #status-tokens {
        width: 1fr;
        color: $text-muted;
    }

    #status-thinking {
        max-width: 15%;
        height: 1;
        color: $warning;
    }
    """

    def compose(self) -> ComposeResult:
        """Construct the status line components.

        Returns:
            A Textual ComposeResult containing mode, model, and token widgets.
        """
        # Mode segment
        yield Static("[bold]ask[/bold]", id="status-mode", markup=True)

        # Separator
        yield Static(" │ ", id="status-separator-1", markup=True)

        # Thinking indicator (hidden by default)
        yield Static("", id="status-thinking", markup=True)

        # Model segment
        yield Static("[dim]model[/dim]", id="status-model", markup=True)

        # Separator
        yield Static(" │ ", id="status-separator-2", markup=True)

        # Token segment
        yield Static(
            "[dim]usage unavailable[/dim]",
            id="status-tokens",
            markup=True,
        )

    def set_mode(self, mode: str) -> None:
        """Update the displayed operational mode.

        Args:
            mode: The name of the new mode (e.g., 'plan', 'code', 'chat').
        """
        mode_widget = self.query_one("#status-mode", Static)

        # Use design token colors based on mode
        if mode == "plan":
            mode_widget.update(f"[$primary]{mode}[/$primary]")
        elif mode == "code":
            mode_widget.update(f"[$secondary]{mode}[/$secondary]")
        elif mode in ("chat", "ask"):
            mode_widget.update(f"[$success]{mode}[/$success]")
        elif mode == "build":
            mode_widget.update(f"[$warning]{mode}[/$warning]")
        else:
            mode_widget.update(f"[bold]{mode}[/bold]")

    def set_thinking(self, is_thinking: bool) -> None:
        """Show or hide the thinking/processing indicator.

        Args:
            is_thinking: Whether the agent is currently processing a request.
        """
        thinking_widget = self.query_one("#status-thinking", Static)
        if is_thinking:
            thinking_widget.update("[$warning]⠋ processing...[/$warning]")
        else:
            thinking_widget.update("")

    def update_usage(self, usage: object) -> None:
        """Replace token and cost measurements, preserving unavailable fields.

        Args:
            usage: A dictionary containing 'total_tokens' and 'estimated_cost_usd'.
        """
        values = usage if isinstance(usage, dict) else {}
        tokens = values.get("total_tokens")
        cost = values.get("estimated_cost_usd")
        tokens_text = "tokens unavailable"
        cost_text = "cost unavailable"

        if not isinstance(tokens, int) or not _is_valid_usage_number(tokens):
            tokens = None
        if not _is_valid_usage_number(cost):
            cost = None
        if tokens is not None:
            tokens_str = f"{tokens / 1000:.1f}K" if tokens >= 1000 else str(tokens)
            tokens_text = f"{tokens_str} tokens"
        if cost is not None:
            cost_text = f"${cost:.4f}"

        usage_text = (
            f"{tokens_text} ({cost_text})"
            if tokens is not None or cost is not None
            else "usage unavailable"
        )
        self.query_one("#status-tokens", Static).update(f"[dim]{usage_text}[/dim]")

    def update_model(self, model_name: str) -> None:
        """Update the displayed model name.

        Args:
            model_name: The name of the current model.
        """
        model_widget = self.query_one("#status-model", Static)
        # Clean up model name for display
        display_name = model_name.replace("gpt-", "").replace("claude-", "")
        model_widget.update(f"[dim]{display_name}[/dim]")


def _is_valid_usage_number(value: object) -> bool:
    """Accept only nonnegative finite numbers that the formatter can represent."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return value >= 0 and math.isfinite(value)
    except OverflowError:
        return False
