"""Dashboard screen for the Agent Terminal UI.

Provides a Homepage-style service dashboard using agent_utilities.gateway
as the data backend. Fetches widget data via the Aggregator streaming API
and renders each service as a styled panel within categorized groups.

Concept: AU-018 (TUI Dashboard Screen)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Static

logger = logging.getLogger(__name__)


# ── Utility: Status icons ────────────────────────────────────────────

_STATUS_ICONS = {
    "ok": "[green]●[/green]",
    "warning": "[yellow]●[/yellow]",
    "error": "[red]●[/red]",
    "unknown": "[dim]○[/dim]",
}


def _status_icon(status: str) -> str:
    return _STATUS_ICONS.get(status, _STATUS_ICONS["unknown"])


# ── ServiceCard ──────────────────────────────────────────────────────

class ServiceCard(Static):
    """A single service card that displays service name, status, and field data."""

    DEFAULT_CSS = """
    ServiceCard {
        width: 1fr;
        min-width: 28;
        max-width: 50;
        height: auto;
        min-height: 7;
        border: solid $primary 20%;
        background: $surface;
        padding: 1 2;
        margin: 0 1 1 0;
    }

    ServiceCard:hover {
        border: solid $primary 60%;
    }

    ServiceCard .card-title {
        text-style: bold;
        width: 100%;
    }

    ServiceCard .card-status {
        color: $text-muted;
        width: 100%;
    }

    ServiceCard .card-field {
        color: $text-muted;
        width: 100%;
    }

    ServiceCard .card-field-value {
        text-style: bold;
        width: 100%;
    }

    ServiceCard .card-error {
        color: $error;
        width: 100%;
    }
    """

    def __init__(
        self,
        service_id: str,
        display_name: str,
        url: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.service_id = service_id
        self.display_name = display_name
        self.url = url
        self._status = "unknown"
        self._fields: list[tuple[str, str]] = []
        self._error: str | None = None

    def compose(self) -> ComposeResult:
        yield Label(
            f"{_status_icon(self._status)} {self.display_name}",
            classes="card-title",
            id=f"title-{self.service_id}",
        )
        yield Label(
            self.url or "—",
            classes="card-status",
            id=f"status-{self.service_id}",
        )
        yield Static(
            "",
            classes="card-field",
            id=f"fields-{self.service_id}",
        )

    def update_data(self, status: str, fields: list[tuple[str, str]], error: str | None = None) -> None:
        """Update card with new widget data."""
        self._status = status
        self._fields = fields
        self._error = error

        with contextlib.suppress(Exception):
            title_label = self.query_one(f"#title-{self.service_id}", Label)
            title_label.update(f"{_status_icon(status)} {self.display_name}")

        if error:
            with contextlib.suppress(Exception):
                field_area = self.query_one(f"#fields-{self.service_id}", Static)
                field_area.update(f"[red]⚠ {error}[/red]")
            return

        if fields:
            lines = []
            for name, value in fields[:6]:  # Max 6 fields for TUI
                lines.append(f"  [dim]{name}:[/dim] [bold]{value}[/bold]")
            field_text = "\n".join(lines)
            with contextlib.suppress(Exception):
                field_area = self.query_one(f"#fields-{self.service_id}", Static)
                field_area.update(field_text)


# ── CategoryGroup ────────────────────────────────────────────────────

class CategoryGroup(Vertical):
    """A collapsible section containing service cards for a single category."""

    DEFAULT_CSS = """
    CategoryGroup {
        width: 100%;
        height: auto;
        margin: 0 0 1 0;
    }

    CategoryGroup .group-header {
        text-style: bold;
        color: $primary;
        padding: 0 1;
        width: 100%;
    }

    CategoryGroup .group-cards {
        layout: horizontal;
        width: 100%;
        height: auto;
    }
    """

    def __init__(self, category_name: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category_name = category_name

    def compose(self) -> ComposeResult:
        yield Label(
            f"▸ {self.category_name.upper()}",
            classes="group-header",
        )
        yield Horizontal(classes="group-cards", id=f"cards-{self.category_name.replace(' ', '-').lower()}")


# ── DashboardScreen ──────────────────────────────────────────────────

class DashboardScreen(Screen):
    """Homepage-style service dashboard screen.

    Displays all configured service widgets in categorized groups,
    with auto-refresh streaming from agent_utilities.gateway Aggregator.
    """

    CSS = """
    DashboardScreen {
        layout: vertical;
    }

    #dashboard-header {
        width: 100%;
        height: 3;
        background: $surface;
        padding: 0 2;
        content-align: center middle;
    }

    #dashboard-header .header-title {
        text-style: bold;
        color: $primary;
    }

    #dashboard-header .header-stats {
        color: $text-muted;
        dock: right;
    }

    #dashboard-scroll {
        width: 100%;
        height: 1fr;
        padding: 1 2;
    }

    #dashboard-empty {
        width: 100%;
        height: 100%;
        content-align: center middle;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("r", "refresh_dashboard", "Refresh", show=True),
        Binding("escape", "go_back", "Back", show=True),
        Binding("q", "go_back", "Quit", show=False),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._aggregator = None
        self._cards: dict[str, ServiceCard] = {}
        self._streaming = False
        self._refresh_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        yield Header()

        # Dashboard header bar
        with Horizontal(id="dashboard-header"):
            yield Label(
                "🏠 Agent-OS Service Dashboard",
                classes="header-title",
            )
            yield Label(
                "Loading...",
                classes="header-stats",
                id="stats-label",
            )

        # Main scrollable content
        yield ScrollableContainer(id="dashboard-scroll")

        yield Footer()

    async def on_mount(self) -> None:
        """Initialize the aggregator and populate the dashboard."""
        await self._init_aggregator()
        await self._populate_dashboard()
        self._start_streaming()

    async def _init_aggregator(self) -> None:
        """Lazy-import and initialize the aggregator."""
        try:
            from agent_utilities.gateway.aggregator import Aggregator
            self._aggregator = Aggregator()
        except ImportError:
            logger.warning(
                "agent-utilities gateway not available — dashboard will show placeholder."
            )

    async def _populate_dashboard(self) -> None:
        """Build the initial dashboard layout from config."""
        container = self.query_one("#dashboard-scroll", ScrollableContainer)

        if not self._aggregator:
            await container.mount(
                Label(
                    "⚠ agent-utilities gateway not available.\n"
                    "Install it with: pip install agent-utilities",
                    id="dashboard-empty",
                )
            )
            return

        # Load layout and build groups
        try:
            layout = self._aggregator.get_layout()
        except Exception as e:
            logger.error("Failed to load dashboard layout: %s", e)
            await container.mount(
                Label(
                    f"⚠ Failed to load dashboard config: {e}",
                    id="dashboard-empty",
                )
            )
            return

        if not layout.groups:
            await container.mount(
                Label(
                    "No services configured.\n"
                    "Add services to $XDG_CONFIG_HOME/agent-os/services.yaml",
                    id="dashboard-empty",
                )
            )
            return

        for group in layout.groups:
            cat_group = CategoryGroup(
                category_name=group.name,
                id=f"group-{group.name.replace(' ', '-').lower()}",
            )
            await container.mount(cat_group)

            cards_container = cat_group.query_one(
                f"#cards-{group.name.replace(' ', '-').lower()}", Horizontal
            )

            for svc in group.services:
                if not svc.visible:
                    continue
                card = ServiceCard(
                    service_id=svc.id,
                    display_name=svc.name,
                    url=svc.url or "",
                    id=f"card-{svc.id}",
                )
                self._cards[svc.id] = card
                await cards_container.mount(card)

        # Update header stats
        total = len(self._cards)
        self._update_stats(total, 0, 0)

        # Initial fetch
        await self._refresh_data()

    async def _refresh_data(self) -> None:
        """Fetch all widget data and update cards."""
        if not self._aggregator:
            return

        try:
            data = await self._aggregator.fetch_all()
        except Exception as e:
            logger.error("Dashboard refresh failed: %s", e)
            return

        ok_count = 0
        err_count = 0

        for svc_id, widget_data in data.items():
            card = self._cards.get(svc_id)
            if not card:
                continue

            fields = []
            if widget_data.fields:
                for f in widget_data.fields:
                    fields.append((f.label, str(f.value)))

            card.update_data(
                status=widget_data.status,
                fields=fields,
                error=widget_data.error,
            )

            if widget_data.status == "ok":
                ok_count += 1
            elif widget_data.status == "error":
                err_count += 1

        self._update_stats(len(self._cards), ok_count, err_count)

    def _update_stats(self, total: int, ok: int, errors: int) -> None:
        """Update the header stats label."""
        with contextlib.suppress(Exception):
            stats_label = self.query_one("#stats-label", Label)
            stats_label.update(
                f"{total} services  |  "
                f"[green]{ok} healthy[/green]  |  "
                f"[red]{errors} errors[/red]"
            )

    def _start_streaming(self) -> None:
        """Start background streaming refresh."""
        if not self._streaming and self._aggregator:
            self._streaming = True
            self._run_stream()

    @work(exclusive=True)
    async def _run_stream(self) -> None:
        """Background worker that periodically refreshes dashboard data."""
        try:
            while self._streaming:
                await asyncio.sleep(30.0)
                await self._refresh_data()
        except asyncio.CancelledError:
            pass

    def action_refresh_dashboard(self) -> None:
        """Manual refresh action (R key)."""
        self.run_worker(self._refresh_data())
        self.notify("Dashboard refreshed", severity="information")

    def action_go_back(self) -> None:
        """Navigate back to the main screen."""
        self._streaming = False
        self.app.pop_screen()

    async def on_unmount(self) -> None:
        """Stop streaming on unmount."""
        self._streaming = False
