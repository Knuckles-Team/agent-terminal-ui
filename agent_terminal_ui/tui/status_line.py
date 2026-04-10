from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

MODE_COLORS: dict[str, str] = {
    "plan": "#b48ead",
    "code": "#7aa2c7",
}

DEFAULT_MODE_COLOR = "#808080"


class StatusLine(Horizontal):
    """Status line displaying mode, model, and token count."""

    def compose(self) -> ComposeResult:
        initial_color = MODE_COLORS.get("plan", DEFAULT_MODE_COLOR)
        yield Static(f"[{initial_color}]plan[/]", id="status-mode", markup=True)
        yield Static("", id="status-thinking", markup=True)
        yield Static("gpt-5.2", id="status-model")
        yield Static("12234 tokens", id="status-tokens")

    def set_mode(self, mode: str) -> None:
        color = MODE_COLORS.get(mode, DEFAULT_MODE_COLOR)
        mode_widget = self.query_one("#status-mode", Static)
        mode_widget.update(f"[{color}]{mode}[/]")

    def set_thinking(self, is_thinking: bool) -> None:
        """Show or hide the thinking indicator."""
        thinking_widget = self.query_one("#status-thinking", Static)
        if is_thinking:
            thinking_widget.update("[bold cyan] Thinking...[/]")
        else:
            thinking_widget.update("")
