"""Searchable live capability catalog for the main-screen sidebar."""

from __future__ import annotations

from typing import Any

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Input, ListItem, ListView, Static

from agent_terminal_ui.capabilities import CapabilityCatalog, CapabilityDescriptor


class CapabilitySidebar(Vertical):
    """Compact capability search with explicit runtime availability states."""

    class CapabilitySelected(Message):
        """Posted when the operator chooses a capability to inspect."""

        def __init__(self, capability_id: str) -> None:
            super().__init__()
            self.capability_id = capability_id

    DEFAULT_CSS = """
    CapabilitySidebar {
        width: 100%;
        height: 100%;
        padding: 0 1;
    }

    #capability-sidebar-header {
        height: 3;
    }

    #capability-sidebar-status {
        width: 1fr;
        height: 3;
        content-align: left middle;
        color: $text-muted;
    }

    #capability-sidebar-refresh {
        width: 9;
        min-width: 9;
        margin: 0;
    }

    #capability-sidebar-search {
        margin-bottom: 1;
    }

    #capability-sidebar-list {
        height: 1fr;
    }

    #capability-sidebar-list ListItem {
        height: auto;
        min-height: 2;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.catalog: CapabilityCatalog | None = None
        self.filtered: list[CapabilityDescriptor] = []
        self.error: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="capability-sidebar-header"):
            yield Static("Not loaded", id="capability-sidebar-status")
            yield Button("Refresh", id="capability-sidebar-refresh", compact=True)
        yield Input(
            placeholder="Search capabilities or actions",
            id="capability-sidebar-search",
        )
        yield ListView(id="capability-sidebar-list")

    def on_mount(self) -> None:
        """Load the live catalog without blocking the conversation screen."""
        self.run_worker(
            self.load_catalog(),
            group="capability-sidebar",
            exclusive=True,
            name="load capability sidebar",
        )

    async def load_catalog(self) -> None:
        """Refresh from the gateway and retain failures as visible state."""
        self.error = None
        self.query_one("#capability-sidebar-status", Static).update("Loading...")
        try:
            catalog = await self.app.agent_client.list_capabilities(
                include_actions=True
            )
        except Exception as exc:
            self.catalog = None
            self.filtered = []
            self.error = f"{type(exc).__name__}: {exc}"
            self.query_one("#capability-sidebar-status", Static).update(
                f"[yellow]Catalog unavailable[/yellow]\n[dim]{escape(self.error)}[/dim]"
            )
            self._render_list()
            return
        self.set_catalog(catalog)

    def set_catalog(self, catalog: CapabilityCatalog) -> None:
        """Install a catalog snapshot and apply the current local search."""
        self.catalog = catalog
        self.error = None
        search = self.query_one("#capability-sidebar-search", Input).value
        self._filter(search)

    def _filter(self, query: str) -> None:
        capabilities = self.catalog.capabilities if self.catalog else ()
        normalized = query.strip().lower()
        self.filtered = [
            capability
            for capability in capabilities
            if not normalized or normalized in capability.search_text
        ]
        self._render_list()

        if self.catalog is None:
            return
        runtime_status = str(self.catalog.runtime.get("status") or "unknown")
        total = len(self.catalog.capabilities)
        shown = min(len(self.filtered), 100)
        self.query_one("#capability-sidebar-status", Static).update(
            f"{shown}/{total} shown\n[dim]Runtime: {escape(runtime_status)}[/dim]"
        )

    def _render_list(self) -> None:
        list_view = self.query_one("#capability-sidebar-list", ListView)
        list_view.clear()
        for capability in self.filtered[:100]:
            availability = capability.availability
            color = {
                "available": "green",
                "degraded": "yellow",
                "unavailable": "red",
            }.get(availability.status, "dim")
            if availability.is_available and availability.readiness == "cold":
                color = "cyan"
            actions = len(capability.actions)
            label = (
                f"[{color}]●[/{color}] [bold]{escape(capability.title)}[/bold]\n"
                f"[dim]{actions} action{'s' if actions != 1 else ''} · "
                f"{escape(availability.display_status)}[/dim]"
            )
            list_view.append(ListItem(Static(label)))
        if self.filtered:
            list_view.index = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "capability-sidebar-search":
            self._filter(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "capability-sidebar-refresh":
            self.run_worker(
                self.load_catalog(), group="capability-sidebar", exclusive=True
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is None or index >= min(len(self.filtered), 100):
            return
        self.post_message(self.CapabilitySelected(self.filtered[index].id))
