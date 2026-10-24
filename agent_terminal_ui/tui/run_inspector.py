"""Mission Control replay and live follow for canonical gateway run events."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Button, DataTable, Input, ListItem, ListView, Static

from agent_terminal_ui.capabilities import (
    RunCatalog,
    RunSummary,
)
from agent_terminal_ui.client import AgentClient
from agent_terminal_ui.display_text import display_text
from agent_terminal_ui.public_run_events import (
    MAX_EVENTS,
    MAX_VIEW_BYTES,
    PublicRunEvent,
    PublicRunPage,
    PublicRunSummary,
)


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

    @staticmethod
    def _run_matches_query(run: RunSummary, normalized_query: str) -> bool:
        """Whether a run's identity/status fields contain the search query."""
        if not normalized_query:
            return True
        haystack = " ".join(
            (
                run.run_id,
                run.session_id or "",
                run.trace_id or "",
                run.status,
                run.last_event_type or "",
            )
        ).lower()
        return normalized_query in haystack

    def _run_browser_status(self, scope: str, catalog: RunCatalog) -> tuple[str, str]:
        """The (message, color) pair for the status bar after filtering."""
        if not catalog.runs:
            return (
                f"No process-local runs are available for {scope}. "
                "The bounded replay store may be empty or restarted.",
                "yellow",
            )
        message = f"{len(self.filtered)} of {len(catalog.runs)} runs ({scope})."
        return message, "green"

    def _filter(self, query: str) -> None:
        runs = self.catalog.runs if self.catalog else ()
        normalized = query.strip().lower()
        self.filtered = [
            run for run in runs if self._run_matches_query(run, normalized)
        ]
        self._render_list()
        if self.catalog is None:
            return
        scope = f"session {self.session_id}" if self.session_id else "all sessions"
        message, color = self._run_browser_status(scope, self.catalog)
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
            RunInspectorScreen(
                self.client,
                self.filtered[index].run_id,
                context_id=getattr(self.app, "current_session_id", None),
            )
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
    """Bounded overview and public event replay from canonical run operations."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("r", "replay", "Replay", show=False),
        Binding("f", "toggle_follow", "Follow", show=False),
        Binding("escape", "close", "Close", show=False),
    ]
    FOLLOW_POLL_INTERVAL = 1.0

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
        context_id: str | None,
        task_id: str | None = None,
        poll_interval: float = FOLLOW_POLL_INTERVAL,
    ) -> None:
        super().__init__()
        self.client, self.run_id, self.task_id = client, run_id, task_id
        self.poll_interval = max(0.01, poll_interval)
        self.summary: PublicRunSummary | None = None
        self.events: list[PublicRunEvent] = []
        self.next_after = 0
        self.following = False
        self.terminal_event_type: str | None = None
        self._follow_generation = 0
        self._owner_context = context_id
        self._owner_invalidated = False

    def compose(self) -> ComposeResult:
        with Vertical(id="run-inspector-dialog"):
            yield Static(
                f"Run inspection: {display_text(self.run_id, multiline=False)}",
                id="run-inspector-title",
                markup=False,
            )
            yield Static(
                "Reading authorized run...", id="run-inspector-status", markup=False
            )
            yield Static(
                "Run overview unavailable", id="run-inspector-summary", markup=False
            )
            yield Static("", id="run-inspector-gap", markup=False)
            yield DataTable(
                id="run-inspector-events", cursor_type="row", zebra_stripes=True
            )
            yield Static(
                "Select a public event.", id="run-inspector-payload", markup=False
            )
            with Horizontal(id="run-inspector-actions"):
                yield Button("Replay from start", id="run-inspector-replay")
                yield Button("Pause follow", id="run-inspector-follow")
                yield Button("Poll now", id="run-inspector-more")
                yield Button("Close", id="run-inspector-close")

    def on_mount(self) -> None:
        self.query_one("#run-inspector-events", DataTable).add_columns(
            "Seq", "Task", "Type"
        )
        self._start_follow(reset=True)

    def _same_owner(self) -> bool:
        return (
            not self._owner_invalidated
            and getattr(self.app, "agent_client", self.client) is self.client
            and getattr(self.app, "current_session_id", None) == self._owner_context
        )

    def _stop(self) -> None:
        self._follow_generation += 1
        self.following = False
        self.workers.cancel_group(self, "run-inspector-follow")

    def _owner_lost(self) -> None:
        if not self._owner_invalidated:
            self._owner_invalidated = True
            self._stop()
            self._clear_protected()
            self.query_one("#run-inspector-status", Static).update(
                "Run inspection unavailable: connection or context changed. "
                "Close and reopen."
            )
            self._sync_follow_controls()

    def on_idle(self) -> None:
        if self.is_mounted and not self._same_owner():
            self._owner_lost()

    def _current(self, generation: int) -> bool:
        if not self.is_mounted or generation != self._follow_generation:
            return False
        if not self._same_owner():
            self._owner_lost()
            return False
        return True

    def action_close(self) -> None:
        self._stop()
        self._clear_protected()
        self.dismiss()

    def on_unmount(self) -> None:
        self._stop()
        self._clear_protected(render=False)

    def action_replay(self) -> None:
        self._start_follow(reset=True)

    def action_toggle_follow(self) -> None:
        if not self._current(self._follow_generation):
            return
        if self.terminal_event_type is not None:
            return
        if self.following:
            self._stop()
            self.query_one("#run-inspector-status", Static).update(
                f"Live follow paused at cursor {self.next_after}; "
                "no terminal event asserted."
            )
            self._sync_follow_controls()
        else:
            self._start_follow(reset=False)

    def _start_follow(self, *, reset: bool, once: bool = False) -> None:
        self._stop()
        if reset:
            self._clear_protected()
        if not self._same_owner():
            self._owner_lost()
            return
        self.following = True
        self.query_one("#run-inspector-status", Static).update(
            "Reading authorized run..."
        )
        self._sync_follow_controls()
        self.run_worker(
            self._follow(self._follow_generation, once=once),
            group="run-inspector-follow",
            exclusive=True,
        )

    def _clear_protected(self, *, render: bool = True) -> None:
        self.summary = None
        self.events.clear()
        self.next_after = 0
        self.terminal_event_type = None
        if render:
            self.query_one("#run-inspector-events", DataTable).clear()
            self.query_one("#run-inspector-summary", Static).update(
                "Run overview unavailable"
            )
            self.query_one("#run-inspector-gap", Static).update("")
            self.query_one("#run-inspector-payload", Static).update(
                "Public event details unavailable."
            )

    async def _follow(self, generation: int, *, once: bool) -> None:
        try:
            while self._current(generation) and self.following:
                more = await self._poll_once(generation)
                if (
                    not self._current(generation)
                    or not self.following
                    or self.terminal_event_type
                    or once
                ):
                    break
                await asyncio.sleep(0 if more else self.poll_interval)
        finally:
            if self._current(generation):
                self.following = False
                self._sync_follow_controls()

    async def _poll_once(self, generation: int) -> bool:
        if not self._current(generation):
            return False
        after = self.next_after
        try:
            summary = await self.client.get_run_summary(
                self.run_id, task_id=self.task_id
            )
            if not self._current(generation):
                return False
            value = await self.client.get_public_run_events(
                self.run_id, task_id=summary.task_id, after=after
            )
            if not self._current(generation):
                return False
            page = PublicRunPage.parse(value, self.run_id, after)
            self._apply_page(page)
            self.summary, self.task_id = summary, summary.task_id
        except Exception:
            if self._current(generation):
                self._clear_protected()
                self.following = False
                self.query_one("#run-inspector-status", Static).update(
                    "Run inspection unavailable: unsupported, refused or invalid "
                    "runs.get/events read. "
                    "Press R to retry. /run plan remains a separate read."
                )
            return False
        self.query_one("#run-inspector-summary", Static).update(
            f"Run: {summary.run_id} · Task: {summary.task_id} · "
            f"Status: {summary.status}\n"
            "Applied configuration, context budget, cost and terminal reason: "
            "unavailable."
        )
        status = (
            f"Public terminal event: {self.terminal_event_type}. Follow stopped."
            if self.terminal_event_type
            else (
                f"Public events: {len(self.events)} retained · "
                f"cursor {self.next_after}."
            )
        )
        self.query_one("#run-inspector-status", Static).update(status)
        return page.has_more

    def _apply_page(self, page: PublicRunPage) -> None:
        retained_ids = {event.event_id for event in self.events}
        if (
            page.next_after < self.next_after
            or (page.events and page.events[0].sequence != self.next_after + 1)
            or any(event.event_id in retained_ids for event in page.events)
        ):
            raise ValueError("public replay regressed or repeated an event")
        self.events.extend(page.events)
        self.events = self.events[-MAX_EVENTS:]
        size = sum(len(event.text.encode()) for event in self.events)
        while self.events and size > MAX_VIEW_BYTES:
            size -= len(self.events.pop(0).text.encode())
        self.next_after = page.next_after
        if page.terminal:
            self.terminal_event_type = next(
                (event.kind for event in reversed(self.events) if event.terminal),
                "server-reported terminal state",
            )
        table = self.query_one("#run-inspector-events", DataTable)
        table.clear()
        for event in self.events:
            table.add_row(
                str(event.sequence),
                Text(event.task_id),
                Text(event.kind),
                key=str(event.sequence),
            )
        omitted = bool(self.events and self.events[0].sequence > 1)
        self.query_one("#run-inspector-gap", Static).update(
            "Earlier events omitted from this bounded view." if omitted else ""
        )
        self.query_one("#run-inspector-payload", Static).update(
            "Select a public event."
        )

    def _sync_follow_controls(self) -> None:
        follow = self.query_one("#run-inspector-follow", Button)
        follow.label = "Pause follow" if self.following else "Resume follow"
        follow.disabled = (
            self._owner_invalidated or self.terminal_event_type is not None
        )
        self.query_one("#run-inspector-more", Button).disabled = (
            self.following or follow.disabled
        )
        self.query_one(
            "#run-inspector-replay", Button
        ).disabled = self._owner_invalidated

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if not self._current(self._follow_generation):
            return
        if (
            event.data_table.id == "run-inspector-events"
            and 0 <= event.cursor_row < len(self.events)
        ):
            self.query_one("#run-inspector-payload", Static).update(
                self.events[event.cursor_row].text
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-inspector-close":
            self.action_close()
        elif not self._current(self._follow_generation):
            return
        elif event.button.id == "run-inspector-replay":
            self.action_replay()
        elif event.button.id == "run-inspector-follow":
            self.action_toggle_follow()
        elif event.button.id == "run-inspector-more":
            self._start_follow(reset=False, once=True)


def current_plan_display(
    value: object, run_id: str, now: datetime
) -> tuple[str, float]:
    """Validate the current-plan wire value before rendering any supplied text."""
    if not isinstance(value, dict):
        raise ValueError("invalid plan read")
    if value.get("availability") == "unavailable" and value.get("snapshot") is None:
        return "Current plan unavailable", 0
    snapshot = value.get("snapshot")
    if value.get("availability") != "available" or not isinstance(snapshot, dict):
        raise ValueError("invalid plan availability")
    revision = snapshot.get("revision")
    if snapshot.get("run_id") != run_id or type(revision) is not int or revision < 0:
        raise ValueError("invalid plan identity or revision")
    observed = snapshot.get("observed_at")
    expires = snapshot.get("expires_at")
    if not isinstance(observed, str) or not isinstance(expires, str):
        raise ValueError("invalid plan timestamps")
    start, end = datetime.fromisoformat(observed), datetime.fromisoformat(expires)
    if start.utcoffset() != timedelta(0) or end.utcoffset() != timedelta(0):
        raise ValueError("plan timestamps must be UTC")
    if not start <= now < end:
        raise ValueError("plan is not current")
    items = snapshot.get("items")
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError("invalid or oversized plan")
    lines = [f"Current plan for {run_id} (revision {revision})"]
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("invalid plan item")
        text, status = item.get("text"), item.get("status")
        if not isinstance(text, str) or not text or len(text) > 4096:
            raise ValueError("invalid plan text")
        if status not in ("pending", "in_progress", "done"):
            raise ValueError("invalid plan item status")
        lines.append(f"{status}: {text}")
    if not items:
        lines.append("Plan is available and empty")
    return "\n".join(lines), (end - now).total_seconds()


class CurrentPlanScreen(ModalScreen[None]):
    """One run's current plan; read failures and expiry erase the projection."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("r", "refresh_plan", "Refresh"),
        Binding("escape", "close", "Close"),
    ]

    def __init__(self, client: AgentClient, run_id: str) -> None:
        super().__init__()
        self.client = client
        self.run_id = run_id
        self._generation = 0
        self._highest_revision = -1
        self._expiry_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static(f"Run: {self.run_id} | R refresh | Esc close", markup=False)
            yield Static("Current plan unavailable", id="current-plan", markup=False)

    def on_mount(self) -> None:
        self.action_refresh_plan()

    def action_refresh_plan(self) -> None:
        if self._expiry_timer is not None:
            self._expiry_timer.stop()
        self._generation += 1
        generation = self._generation
        self.query_one("#current-plan", Static).update("Loading current plan…")
        self.run_worker(
            self._read_plan(generation), group="current-plan", exclusive=True
        )

    async def _read_plan(self, generation: int) -> None:
        try:
            value = await self.client.get_current_plan(self.run_id)
            text, ttl = current_plan_display(value, self.run_id, datetime.now(UTC))
            if ttl > 0:
                revision = value["snapshot"]["revision"]
                if revision < self._highest_revision:
                    raise ValueError("plan revision regressed")
                if generation == self._generation:
                    self._highest_revision = revision
        except Exception:
            text, ttl = "Current plan unavailable", 0
        if not self.is_mounted or generation != self._generation:
            return
        self.query_one("#current-plan", Static).update(text)
        if ttl > 0:
            self._expiry_timer = self.set_timer(ttl, lambda: self._expire(generation))

    def _expire(self, generation: int) -> None:
        if self.is_mounted and generation == self._generation:
            self.query_one("#current-plan", Static).update(
                "Current plan unavailable: expired"
            )

    def action_close(self) -> None:
        self._generation += 1
        if self._expiry_timer is not None:
            self._expiry_timer.stop()
        self.dismiss()
