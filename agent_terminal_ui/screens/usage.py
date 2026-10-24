"""Local estimates and caller-tenant usage from Arbora usage.read."""

from __future__ import annotations

import math

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Static
from textual.worker import get_current_worker


def _fmt_usd(n: float) -> str:
    return f"${(n or 0):.2f}"


def _fmt_num(n: int) -> str:
    n = n or 0
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


class UsageScreen(Screen):
    """Live + historical usage/cost dashboard."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=True),
        Binding("escape", "go_back", "Back", show=True),
        Binding("q", "go_back", "Quit", show=False),
    ]

    DEFAULT_CSS = """
    UsageScreen { background: $surface; }
    #usage-scroll { padding: 1 2; }
    .usage-section { color: $primary; text-style: bold; margin: 1 0 0 0; }
    .usage-kpi { color: $text; margin: 0 0 1 0; }
    DataTable { margin: 0 0 1 0; height: auto; max-height: 16; }
    #usage-heatmap { color: $text-muted; margin: 0 0 1 0; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("💰 Usage & Cost", classes="usage-section")
        with ScrollableContainer(id="usage-scroll"):
            yield Static("", id="usage-live", classes="usage-kpi")
            yield Label("Caller tenant (served usage)", classes="usage-section")
            yield Static("Loading…", id="usage-hist", classes="usage-kpi", markup=False)
            yield Static(
                "Per-turn and served session totals: unavailable", markup=False
            )
        yield Footer()

    def on_mount(self) -> None:
        self._render_live()
        self.refresh_usage()

    # ── live (local cost_tracker, no network) ──────────────────────────
    def _render_live(self) -> None:
        tracker = getattr(self.app, "cost_tracker", None)
        widget = self.query_one("#usage-live", Static)
        if tracker is None:
            widget.update(
                "[dim]This session (local estimate): no local cost tracker[/dim]"
            )
            return
        try:
            s = tracker.get_session_summary()
            line = (
                f"[bold]This session (local estimate)[/bold]  "
                f"turns={s.total_turns}  "
                f"in={_fmt_num(s.total_input_tokens)}  "
                f"out={_fmt_num(s.total_output_tokens)}  "
                f"cost={_fmt_usd(s.total_cost_usd)}  "
                f"cache={s.cache_hit_rate * 100:.0f}%"
            )
            widget.update(line)
        except Exception as e:  # noqa: BLE001
            widget.update(f"[dim]live summary unavailable: {e}[/dim]")

    # ── historical (gateway) ───────────────────────────────────────────
    @work(exclusive=True)
    async def refresh_usage(self) -> None:
        worker = get_current_worker()
        widget = self.query_one("#usage-hist", Static)
        widget.update("Loading usage.read…")
        client = getattr(self.app, "agent_client", None)
        if client is None:
            widget.update("usage.read unavailable: no client")
            return
        try:
            snapshot = await client.get_usage_summary()
            if worker.is_cancelled or not self.is_mounted:
                return
            totals = snapshot.get("totals")
            if not isinstance(totals, dict) or not totals:
                widget.update("usage.read: tenant totals unavailable")
                return
            if any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                for value in totals.values()
            ):
                widget.update("usage.read unavailable: invalid totals")
                return
            widget.update(
                "\n".join(f"{name}: {value}" for name, value in totals.items())
            )
        except Exception as exc:
            if not worker.is_cancelled and self.is_mounted:
                widget.update(f"usage.read unavailable: {exc}")

    def action_refresh(self) -> None:
        self._render_live()
        self.refresh_usage()

    def check_consume_key(self, key: str, character: str | None) -> bool:
        """Keep the screen close key from reaching application rewind."""
        return key == "escape" or super().check_consume_key(key, character)

    def action_go_back(self) -> None:
        self.app.pop_screen()
