"""Usage & Cost screen for Agent Terminal UI.

CONCEPT:AU-ECO.mcp.usage-cost-observability-surface

Two clearly-labeled regions:
  * "This session (live)" — the local per-session ``CostTracker`` (no network).
  * "All agents (historical)" — the gateway /api/observability/* surface, across
    every ingested agent + our own runtime telemetry.

Modeled on DashboardScreen (Screen + @work refresh). Opened with Alt+U or the
``/usage`` command.
"""

from __future__ import annotations

import logging
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label, Static

logger = logging.getLogger(__name__)

_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_BLOCKS = " ▁▂▃▄▅▆▇█"


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
            yield Label("All agents (historical)", classes="usage-section")
            yield Static("Loading…", id="usage-hist", classes="usage-kpi")
            yield DataTable(id="usage-models")
            yield DataTable(id="usage-tools")
            yield Static("", id="usage-heatmap")
            yield DataTable(id="usage-sessions")
            yield Static("", id="usage-traces")
        yield Footer()

    def on_mount(self) -> None:
        self._render_live()
        self.refresh_usage()

    # ── live (local cost_tracker, no network) ──────────────────────────
    def _render_live(self) -> None:
        tracker = getattr(self.app, "cost_tracker", None)
        widget = self.query_one("#usage-live", Static)
        if tracker is None:
            widget.update("[dim]This session (live): no local cost tracker[/dim]")
            return
        try:
            s = tracker.get_session_summary()
            line = (
                f"[bold]This session (live)[/bold]  "
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
        client = getattr(self.app, "agent_client", None)
        if client is None:
            self.query_one("#usage-hist", Static).update("[red]No gateway client[/red]")
            return
        try:
            summary = await client.get_usage_summary(origin="ingested")
            by_model = await client.get_usage_by_model()
            tools = await client.get_usage_tools()
            activity = await client.get_usage_activity()
            sessions = await client.get_usage_top_sessions(limit=15)
            traces = await client.get_usage_traces()
        except Exception as e:  # noqa: BLE001
            self.query_one("#usage-hist", Static).update(
                f"[red]gateway error: {e}[/red]"
            )
            return

        totals = (summary or {}).get("totals", {})
        self.query_one("#usage-hist", Static).update(
            f"sessions={summary.get('session_count', 0)}  "
            f"in={_fmt_num(totals.get('input_tokens', 0))}  "
            f"out={_fmt_num(totals.get('output_tokens', 0))}  "
            f"cost={_fmt_usd(totals.get('cost_usd', 0))}  "
            f"cache={summary.get('cache_hit_rate', 0) * 100:.0f}%"
        )
        self._fill_models(by_model)
        self._fill_tools(tools)
        self._fill_heatmap(activity)
        self._fill_sessions(sessions)
        self._fill_traces(traces)

    def _fill_models(self, rows: list[dict[str, Any]]) -> None:
        t = self.query_one("#usage-models", DataTable)
        t.clear(columns=True)
        t.add_columns("Model", "Sessions", "Tokens", "Cost")
        for r in rows[:20]:
            t.add_row(
                r.get("key", "?"),
                str(r.get("session_count", 0)),
                _fmt_num(r.get("input_tokens", 0) + r.get("output_tokens", 0)),
                _fmt_usd(r.get("cost_usd", 0)),
            )

    def _fill_tools(self, rows: list[dict[str, Any]]) -> None:
        t = self.query_one("#usage-tools", DataTable)
        t.clear(columns=True)
        t.add_columns("Tool/Skill", "Category", "Calls", "Success")
        for r in rows[:20]:
            t.add_row(
                r.get("name", "?"),
                r.get("category", "other"),
                str(r.get("calls", 0)),
                f"{r.get('success_rate', 0) * 100:.0f}%",
            )

    def _fill_heatmap(self, cells: list[dict[str, Any]]) -> None:
        grid = {(c["day_of_week"], c["hour"]): c["sessions"] for c in cells}
        mx = max([v for v in grid.values()], default=1) or 1
        lines = ["[bold]Activity (day × hour)[/bold]"]
        for di, day in enumerate(_DAYS):
            row = []
            for h in range(24):
                v = grid.get((di, h), 0)
                idx = 0 if v == 0 else min(8, 1 + int(v / mx * 7))
                row.append(_BLOCKS[idx])
            lines.append(f"{day} {''.join(row)}")
        self.query_one("#usage-heatmap", Static).update("\n".join(lines))

    def _fill_sessions(self, rows: list[dict[str, Any]]) -> None:
        t = self.query_one("#usage-sessions", DataTable)
        t.clear(columns=True)
        t.add_columns("Project", "Agent", "Msgs", "Cost", "Grade")
        for r in rows[:15]:
            t.add_row(
                (r.get("project") or "—")[:40],
                r.get("agent", "?"),
                str(r.get("message_count", 0)),
                _fmt_usd(r.get("cost_usd", 0)),
                r.get("health_grade") or "",
            )

    def _fill_traces(self, traces: dict[str, Any]) -> None:
        widget = self.query_one("#usage-traces", Static)
        if not traces.get("enabled"):
            widget.update("")
            return
        lines = [f"[bold]Langfuse[/bold] ({traces.get('host', '')})"]
        for tr in traces.get("traces", [])[:10]:
            lines.append(f"  {tr.get('session_id', '')[:16]}  {tr.get('url', '')}")
        widget.update("\n".join(lines))

    def action_refresh(self) -> None:
        self._render_live()
        self.refresh_usage()

    def action_go_back(self) -> None:
        self.app.pop_screen()
