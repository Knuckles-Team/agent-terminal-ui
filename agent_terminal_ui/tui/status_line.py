#!/usr/bin/python
"""Status line component for the terminal UI.

Displays session metadata such as the current interaction mode,
active model information, token usage, and a thinking indicator.
Uses Textual design tokens for consistent theming.

Concept: AU-018 (TUI Status Line)
"""

import math
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class StatusLine(Horizontal):
    """Bottom status line for the Agent Terminal UI.

    Maintains visual indicators for the current application state,
    including agent processing status and configured operational mode,
    using Textual design tokens for theme consistency.
    """

    _turn_usage: dict[str, Any] | None = None

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
            usage: A decoded turn receipt or legacy token/cost measurements.
        """
        values = usage if isinstance(usage, dict) else {}
        widget = self.query_one("#status-tokens", Static)
        self._turn_usage = values if values.get("scope") == "turn" else None
        if self._turn_usage is not None:
            counts = values.get("counts")
            summary = "Turn usage: unavailable"
            if isinstance(counts, dict):
                summary = "Turn tokens: " + ", ".join(
                    f"{counts.get(key, 'unavailable')} {label}"
                    for key, label in (
                        ("input_tokens", "in"),
                        ("output_tokens", "out"),
                        ("total_tokens", "total"),
                    )
                )
            summary += " | Session usage: unavailable | Cost: unavailable"
            if self.size.width < 60:
                total = (
                    counts.get("total_tokens", "unavailable")
                    if isinstance(counts, dict)
                    else "unavailable"
                )
                summary = f"Turn tokens: {total}"
            widget.update(Text(summary, style="dim"))
            widget.tooltip = turn_usage_text(values)
            return
        widget.tooltip = None
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

    def on_resize(self) -> None:
        """Keep narrow turn summaries bounded while retaining exact details."""
        if self._turn_usage is not None:
            self.update_usage(self._turn_usage)

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


def turn_usage_text(usage: dict[str, Any]) -> str:
    """Render a decoded turn receipt without deriving session totals or cost."""
    counts = usage.get("counts")
    lines = ["Turn usage: unavailable"]
    if isinstance(counts, dict):
        lines = ["Turn usage:"]
        lines.extend(
            f"{label}: {counts.get(key, 'unavailable')}"
            for key, label in (
                ("requests", "Requests"),
                ("tool_calls", "Tool calls"),
                ("input_tokens", "Input tokens"),
                ("output_tokens", "Output tokens"),
                ("total_tokens", "Total tokens"),
            )
        )
    return "\n".join([*lines, "Session usage: unavailable", "Cost: unavailable"])
