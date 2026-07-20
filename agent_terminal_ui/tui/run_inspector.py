"""Mission Control replay and live follow for canonical gateway run events."""

from __future__ import annotations

import asyncio
import json
from typing import ClassVar

from rich.markup import escape
from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, ListItem, ListView, Static

from agent_terminal_ui.capabilities import (
    RunCatalog,
    RunEvent,
    RunEventPage,
    RunReplayGap,
    RunSummary,
)
from agent_terminal_ui.client import AgentClient


class RunBrowserScreen(ModalScreen[None]):
    """Discover newest-first canonical runs before opening event replay."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    RunBrowserScreen {
        align: center middle;
    }

    #run-browser-dialog {
        width: 86%;
        height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }

    #run-browser-title {
        height: 2;
        text-align: center;
        text-style: bold;
        color: $primary;
    }

    #run-browser-status {
        height: auto;
        min-height: 2;
        color: $text-muted;
    }

    #run-browser-search {
        height: 3;
    }

    #run-browser-list {
        height: 1fr;
        margin: 1 0;
    }

    #run-browser-list ListItem {
        height: auto;
        min-height: 2;
        padding: 0 1;
    }

    #run-browser-actions {
        height: 3;
        align-horizontal: right;
    }
    """

    def __init__(self, client: AgentClient, *, session_id: str | None = None) -> None:
        super().__init__()
        self.client = client
        self.session_id = session_id
        self.catalog: RunCatalog | None = None
        self.filtered: list[RunSummary] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="run-browser-dialog"):
            yield Static("Mission Control: Recent Runs", id="run-browser-title")
            yield Static("Loading runs...", id="run-browser-status")
            yield Input(
                placeholder="Search run ID, session, status, or event type",
                id="run-browser-search",
            )
            yield ListView(id="run-browser-list")
            with Horizontal(id="run-browser-actions"):
                yield Button("All sessions", id="run-browser-all")
                yield Button("Refresh", id="run-browser-refresh")
                yield Button("Close", id="run-browser-close")

    def on_mount(self) -> None:
        self.run_worker(
            self._load_runs(),
            group="run-browser-load",
            exclusive=True,
            name="load recent runs",
        )

    def action_close(self) -> None:
        self.dismiss()

    async def _load_runs(self) -> None:
        scope = f"session {self.session_id}" if self.session_id else "all sessions"
        self.query_one("#run-browser-status", Static).update(
            f"Loading newest runs for {escape(scope)}..."
        )
        try:
            self.catalog = await self.client.list_runs(
                session_id=self.session_id, limit=100
            )
        except Exception as exc:
            self.catalog = None
            self.filtered = []
            self.query_one("#run-browser-status", Static).update(
                "[yellow]Run discovery unavailable.[/yellow] "
                f"[dim]{escape(f'{type(exc).__name__}: {exc}')}[/dim]"
            )
            self._render_list()
            return
        query = self.query_one("#run-browser-search", Input).value
        self._filter(query)

    def _filter(self, query: str) -> None:
        runs = self.catalog.runs if self.catalog else ()
        normalized = query.strip().lower()
        self.filtered = [
            run
            for run in runs
            if not normalized
            or normalized
            in " ".join(
                (
                    run.run_id,
                    run.session_id or "",
                    run.trace_id or "",
                    run.status,
                    run.last_event_type or "",
                )
            ).lower()
        ]
        self._render_list()
        if self.catalog is None:
            return
        scope = f"session {self.session_id}" if self.session_id else "all sessions"
        if not self.catalog.runs:
            message = (
                f"No process-local runs are available for {scope}. "
                "The bounded replay store may be empty or restarted."
            )
            color = "yellow"
        else:
            message = (
                f"{len(self.filtered)} of {len(self.catalog.runs)} runs ({scope})."
            )
            color = "green"
        self.query_one("#run-browser-status", Static).update(
            f"[{color}]{escape(message)}[/{color}]"
        )

    def _render_list(self) -> None:
        list_view = self.query_one("#run-browser-list", ListView)
        list_view.clear()
        for run in self.filtered:
            color = {
                "running": "cyan",
                "completed": "green",
                "failed": "red",
                "cancelled": "yellow",
                "waiting_for_input": "yellow",
            }.get(run.status, "dim")
            truncated = " · truncated" if run.truncated else ""
            list_view.append(
                ListItem(
                    Static(
                        f"[{color}]● {escape(run.status)}[/{color}] "
                        f"[bold]{escape(run.run_id)}[/bold]\n"
                        f"[dim]{run.event_count} events · "
                        f"{escape(run.session_id or 'no session')}{truncated}[/dim]"
                    )
                )
            )
        if self.filtered:
            list_view.index = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "run-browser-search":
            self._filter(event.value)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "run-browser-list":
            return
        index = event.list_view.index
        if index is None or index >= len(self.filtered):
            return
        self.app.push_screen(
            RunInspectorScreen(self.client, self.filtered[index].run_id)
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-browser-close":
            self.action_close()
        elif event.button.id == "run-browser-all":
            self.session_id = None
            self.run_worker(self._load_runs(), group="run-browser-load", exclusive=True)
        elif event.button.id == "run-browser-refresh":
            self.run_worker(self._load_runs(), group="run-browser-load", exclusive=True)


class RunInspectorScreen(ModalScreen[None]):
    """Mission Control view for replaying and following one canonical run."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("r", "replay", "Replay", show=False),
        Binding("f", "toggle_follow", "Follow", show=False),
        Binding("escape", "close", "Close", show=False),
    ]
    FOLLOW_POLL_INTERVAL = 1.0
    PAGE_LIMIT = 1_000

    DEFAULT_CSS = """
    RunInspectorScreen {
        align: center middle;
    }

    #run-inspector-dialog {
        width: 94%;
        height: 88%;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }

    #run-inspector-title {
        height: 2;
        text-align: center;
        text-style: bold;
        color: $primary;
    }

    #run-inspector-status,
    #run-inspector-summary,
    #run-inspector-gap {
        height: auto;
        min-height: 2;
        padding: 0 1;
    }

    #run-inspector-gap {
        color: $warning;
    }

    #run-inspector-events {
        height: 1fr;
        margin: 1 0;
    }

    #run-inspector-payload {
        height: 10;
        border-top: solid $primary 30%;
        padding: 1;
        overflow-y: auto;
    }

    #run-inspector-actions {
        height: 3;
        align-horizontal: right;
    }
    """

    def __init__(
        self,
        client: AgentClient,
        run_id: str,
        *,
        poll_interval: float = FOLLOW_POLL_INTERVAL,
    ) -> None:
        super().__init__()
        self.client = client
        self.run_id = run_id
        self.poll_interval = max(0.01, poll_interval)
        self.summary: RunSummary | None = None
        self.events: list[RunEvent] = []
        self.next_after = 0
        self.following = False
        self.terminal_event_type: str | None = None
        self.replay_gaps: list[RunReplayGap] = []
        self._seen_sequences: set[int] = set()
        self._follow_generation = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="run-inspector-dialog"):
            yield Static(
                f"Mission Control: {escape(self.run_id)}",
                id="run-inspector-title",
            )
            yield Static("Starting live follow...", id="run-inspector-status")
            yield Static("", id="run-inspector-summary")
            yield Static("", id="run-inspector-gap")
            yield DataTable(
                id="run-inspector-events", cursor_type="row", zebra_stripes=True
            )
            yield Static(
                "Select an event to inspect its canonical payload.",
                id="run-inspector-payload",
            )
            with Horizontal(id="run-inspector-actions"):
                yield Button("Replay from start", id="run-inspector-replay")
                yield Button("Pause follow", id="run-inspector-follow")
                yield Button("Poll now", id="run-inspector-more")
                yield Button("Close", id="run-inspector-close")

    def on_mount(self) -> None:
        table = self.query_one("#run-inspector-events", DataTable)
        table.add_columns("Seq", "Timestamp", "Type", "Source")
        self._start_follow(reset=True)

    def action_close(self) -> None:
        self._follow_generation += 1
        self.following = False
        self.dismiss()

    def action_replay(self) -> None:
        self._start_follow(reset=True)

    def action_toggle_follow(self) -> None:
        if self.terminal_event_type is not None:
            return
        if self.following:
            self._follow_generation += 1
            self.following = False
            self.query_one("#run-inspector-status", Static).update(
                f"[yellow]Live follow paused.[/yellow] "
                f"[dim]Cursor: {self.next_after}; the run is not marked terminal.[/dim]"
            )
            self._sync_follow_controls()
            return
        self._start_follow(reset=False)

    def _start_follow(self, *, reset: bool) -> None:
        self._follow_generation += 1
        generation = self._follow_generation
        self.run_worker(
            self._follow(reset=reset, generation=generation),
            group="run-inspector-follow",
            exclusive=True,
            name="follow canonical run events",
        )

    def _reset_replay(self) -> None:
        self.events = []
        self.next_after = 0
        self.terminal_event_type = None
        self.replay_gaps = []
        self._seen_sequences = set()
        self.query_one("#run-inspector-events", DataTable).clear()
        self.query_one("#run-inspector-gap", Static).update("")
        self.query_one("#run-inspector-payload", Static).update(
            "Select an event to inspect its canonical payload."
        )

    async def _follow(self, *, reset: bool, generation: int) -> None:
        if reset:
            self._reset_replay()
        self.following = True
        self._sync_follow_controls()
        try:
            while (
                self.following
                and generation == self._follow_generation
                and self.terminal_event_type is None
            ):
                has_more = await self._poll_once()
                if self.terminal_event_type is not None:
                    break
                # Drain retained backlog immediately; wait only at its live edge.
                await asyncio.sleep(0 if has_more else self.poll_interval)
        finally:
            if generation == self._follow_generation:
                self.following = False
            if self.is_mounted and generation == self._follow_generation:
                self._sync_follow_controls()

    async def _poll_once(self) -> bool:
        after = self.next_after
        summary_error: str | None = None
        event_error: str | None = None

        try:
            self.summary = await self.client.get_run_summary(self.run_id)
        except Exception as exc:
            self.summary = None
            summary_error = f"{type(exc).__name__}: {exc}"

        try:
            page = await self.client.get_run_events(
                self.run_id, after=after, limit=self.PAGE_LIMIT
            )
        except Exception as exc:
            page = None
            event_error = f"{type(exc).__name__}: {exc}"

        if page is not None:
            self._apply_page(page)

        self._render_summary(summary_error)
        self._render_follow_status(event_error)
        self._sync_follow_controls()
        return bool(page and page.has_more and page.events)

    def _apply_page(self, page: RunEventPage) -> None:
        gap = page.replay_gap
        if gap is not None and gap not in self.replay_gaps:
            self.replay_gaps.append(gap)
            self._render_replay_gaps()

        new_events: list[RunEvent] = []
        for event in sorted(page.events, key=lambda item: item.sequence):
            if event.sequence in self._seen_sequences:
                continue
            self._seen_sequences.add(event.sequence)
            new_events.append(event)

        self.events.extend(new_events)
        sequences = [event.sequence for event in new_events]
        self.next_after = max([self.next_after, page.next_after, *sequences])
        table = self.query_one("#run-inspector-events", DataTable)
        for event in new_events:
            table.add_row(
                str(event.sequence),
                event.timestamp[:19] or "-",
                event.type,
                event.source,
                key=str(event.sequence),
            )
            if self.terminal_event_type is None and event.is_terminal:
                self.terminal_event_type = event.type

    def _render_replay_gaps(self) -> None:
        messages = "\n".join(gap.message for gap in self.replay_gaps[-3:])
        self.query_one("#run-inspector-gap", Static).update(
            f"[yellow]{escape(messages)}[/yellow]"
        )

    def _render_follow_status(self, event_error: str | None) -> None:
        status = self.query_one("#run-inspector-status", Static)
        if self.terminal_event_type is not None:
            status.update(
                "[green]Canonical terminal event reached:[/green] "
                f"[bold]{escape(self.terminal_event_type)}[/bold]. "
                f"[dim]Follow stopped at cursor {self.next_after}.[/dim]"
            )
            return
        if event_error:
            mode = (
                "Live follow degraded; retrying."
                if self.following
                else "Replay poll failed; follow remains paused."
            )
            status.update(
                f"[yellow]{mode}[/yellow] "
                f"[dim]{escape(event_error)} · cursor {self.next_after}; "
                "the run is not marked terminal.[/dim]"
            )
            return
        if not self.events:
            qualifier = (
                "Waiting for the first replayable event."
                if self.summary is not None
                else "Run summary unavailable; retrying the bounded event window."
            )
            mode = "Live follow active." if self.following else "Replay poll complete."
            status.update(f"[cyan]{mode}[/cyan] [dim]{escape(qualifier)}[/dim]")
            return
        latest = self.events[-1].type
        progress = (
            " · graph/output progress; awaiting a run terminal event"
            if latest in {"graph_complete", "final_output"}
            else ""
        )
        mode = "Live follow active." if self.following else "Replay poll complete."
        status.update(
            f"[cyan]{mode}[/cyan] "
            f"[green]{len(self.events)} deduplicated events.[/green] "
            f"[dim]Cursor: {self.next_after} · latest: {escape(latest)}"
            f"{progress}[/dim]"
        )

    def _sync_follow_controls(self) -> None:
        follow = self.query_one("#run-inspector-follow", Button)
        poll = self.query_one("#run-inspector-more", Button)
        if self.terminal_event_type is not None:
            follow.label = "Run terminal"
            follow.disabled = True
            poll.disabled = True
        elif self.following:
            follow.label = "Pause follow"
            follow.disabled = False
            poll.disabled = True
        else:
            follow.label = "Resume follow"
            follow.disabled = False
            poll.disabled = False

    def _render_summary(self, error: str | None) -> None:
        widget = self.query_one("#run-inspector-summary", Static)
        if self.summary is None:
            message = "Run summary unavailable"
            if error:
                message += f": {error}"
            widget.update(f"[yellow]{escape(message)}[/yellow]")
            return
        summary = self.summary
        truncation = (
            " · [yellow]bounded history truncated[/yellow]" if summary.truncated else ""
        )
        widget.update(
            f"Status: {escape(summary.status)} · "
            f"Session: {escape(summary.session_id or 'not reported')} · "
            f"Events: {summary.event_count} · "
            f"Sequences: {summary.first_sequence}-{summary.last_sequence} · "
            f"Last type: {escape(summary.last_event_type or 'unknown')}"
            f"{truncation}"
        )

    def _show_payload(self, row_index: int) -> None:
        if row_index < 0 or row_index >= len(self.events):
            return
        event = self.events[row_index]
        payload = {
            "schema_version": event.schema_version,
            "event_id": event.event_id,
            "sequence": event.sequence,
            "timestamp": event.timestamp,
            "type": event.type,
            "run_id": event.run_id,
            "session_id": event.session_id,
            "trace_id": event.trace_id,
            "correlation_id": event.correlation_id,
            "parent_event_id": event.parent_event_id,
            "source": event.source,
            "payload": event.payload,
        }
        self.query_one("#run-inspector-payload", Static).update(
            Syntax(
                json.dumps(payload, indent=2, sort_keys=True, default=str),
                "json",
                word_wrap=True,
            )
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._show_payload(event.cursor_row)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._show_payload(event.cursor_row)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-inspector-close":
            self.action_close()
        elif event.button.id == "run-inspector-replay":
            self.action_replay()
        elif event.button.id == "run-inspector-follow":
            self.action_toggle_follow()
        elif event.button.id == "run-inspector-more":
            self.run_worker(
                self._poll_once(),
                group="run-inspector-follow",
                exclusive=True,
            )
