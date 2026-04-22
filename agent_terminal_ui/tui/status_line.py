#!/usr/bin/python
"""Status line component for the terminal UI.

Displays session metadata such as the current interaction mode,
active model information, token usage, and a thinking indicator
following modern terminal UI design principles:
- Minimal aesthetics: No powerline separators or emojis
- Semantic colors: State communication through color
- Clear hierarchy: Important information prominent
- Calm design: Focus on content over decoration
"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class StatusLine(Horizontal):
    """Bottom status line for the Agent Terminal UI with minimal design.

    Maintains visual indicators for the current application state,
    including agent processing status and configured operational mode,
    using restraint principles and semantic colors.
    """

    def compose(self) -> ComposeResult:
        """Construct the status line components with minimal styling.

        Returns:
            A Textual ComposeResult containing mode, model, and token widgets
            with semantic colors and clear hierarchy.
        """
        # Mode segment (semantic color based on mode)
        yield Static("[bold]plan[/bold]", id="status-mode", markup=True)

        # Separator (simple vertical bar)
        yield Static(" | ", id="status-separator-1", markup=True)

        # Thinking indicator (hidden by default)
        yield Static("", id="status-thinking", markup=True)

        # Model segment (muted color)
        yield Static("[dim]gpt-5.2[/dim]", id="status-model", markup=True)

        # Separator
        yield Static(" | ", id="status-separator-2", markup=True)

        # Token segment (muted color)
        yield Static("[dim]12234 tokens[/dim]", id="status-tokens", markup=True)

    def set_mode(self, mode: str) -> None:
        """Update the displayed operational mode with semantic styling.

        Args:
            mode: The name of the new mode (e.g., 'plan', 'code', 'chat').

        """
        # Display mode with semantic color
        mode_widget = self.query_one("#status-mode", Static)

        # Use semantic colors based on mode
        if mode == "plan":
            mode_widget.update("[bold #cba6f7]plan[/bold #cba6f7]")
        elif mode == "code":
            mode_widget.update("[bold #89b4fa]code[/bold #89b4fa]")
        elif mode in ("chat", "ask"):
            mode_widget.update("[bold #a6e3a1]chat[/bold #a6e3a1]")
        elif mode == "build":
            mode_widget.update("[bold #fab387]build[/bold #fab387]")
        else:
            mode_widget.update(f"[bold]{mode}[/bold]")

    def set_thinking(self, is_thinking: bool) -> None:
        """Show or hide the thinking/processing indicator.

        Args:
            is_thinking: Whether the agent is currently processing a request.

        """
        thinking_widget = self.query_one("#status-thinking", Static)
        if is_thinking:
            # Minimal thinking indicator
            thinking_widget.update("[bold #f38ba8] processing...[/bold #f38ba8]")
        else:
            thinking_widget.update("")

    def update_usage(self, usage: dict) -> None:
        """Update the displayed token count and cost.

        Args:
            usage: A dictionary containing 'total_tokens' and 'estimated_cost_usd'.

        """
        tokens = usage.get("total_tokens", 0)
        cost = usage.get("estimated_cost_usd", 0.0)
        tokens_widget = self.query_one("#status-tokens", Static)

        # Format large numbers with K suffix
        if tokens >= 1000:
            tokens_str = f"{tokens / 1000:.1f}K"
        else:
            tokens_str = str(tokens)

        # Minimal display with muted color
        tokens_widget.update(f"[dim]{tokens_str} tokens (${cost:.4f})[/dim]")

    def update_model(self, model_name: str) -> None:
        """Update the displayed model name.

        Args:
            model_name: The name of the current model.

        """
        model_widget = self.query_one("#status-model", Static)
        # Clean up model name for display
        display_name = model_name.replace("gpt-", "").replace("claude-", "")
        model_widget.update(f"[dim]{display_name}[/dim]")
