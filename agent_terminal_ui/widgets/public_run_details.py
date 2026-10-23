"""Inline collapsed public summaries and execution facts for one bound turn."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalGroup
from textual.widgets import Collapsible, Static

from agent_terminal_ui.client import ArboraOperationError
from agent_terminal_ui.public_run_events import (
    MAX_EVENTS,
    MAX_VIEW_BYTES,
    PublicRunEvent,
    PublicRunPage,
)

if TYPE_CHECKING:
    from agent_terminal_ui.client import AgentClient


class PublicRunDetails(VerticalGroup):
    """Read public run records lazily without changing a task or its fold choices."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("r", "replay", "Refresh public details", show=False),
    ]
    DEFAULT_CSS = """
    PublicRunDetails { height: auto; margin-bottom: 1; }
    PublicRunDetails Static { height: auto; }
    """
    POLL_INTERVAL = 1.0

    def __init__(self, client: AgentClient, run_id: str | None, task_id: str) -> None:
        super().__init__()
        self.client, self.run_id, self.task_id = client, run_id, task_id
        self.records: list[PublicRunEvent] = []
        self.next_after = 0
        self.terminal = False
        self._generation = 0
        self._reading = False
        self._valid = True
        self._identity = Static(self._identity_label(), markup=False)
        self._summary = Static(
            "Public model summary unavailable until read.", markup=False
        )
        self._trace = Static("Execution trace unavailable until read.", markup=False)
        self.summary_fold = Collapsible(
            self._summary, title="Public model summary", collapsed=True
        )
        self.trace_fold = Collapsible(
            self._trace, title="Execution trace", collapsed=True
        )

    def compose(self) -> ComposeResult:
        yield self._identity
        yield self.summary_fold
        yield self.trace_fold

    def _identity_label(self) -> str:
        return f"Task {self.task_id} · Run {self.run_id or 'unavailable'}"

    def bind_run(self, run_id: str) -> None:
        """Enrich a task-only placeholder with an authoritative server run id."""
        if self._valid and self.run_id is None:
            self.run_id = run_id
            self._identity.update(self._identity_label())
            if not (self.summary_fold.collapsed and self.trace_fold.collapsed):
                self._start()

    def on_key(self, event: events.Key) -> None:
        focused = self.app.focused
        if event.key == "space" and focused is not None:
            fold = focused.parent
            if fold in (self.summary_fold, self.trace_fold):
                event.stop()
                event.prevent_default()
                fold.collapsed = not fold.collapsed

    @on(Collapsible.Toggled)
    def _fold_changed(self, event: Collapsible.Toggled) -> None:
        event.stop()
        if self.summary_fold.collapsed and self.trace_fold.collapsed:
            self._stop()
        elif not self._reading and not self.terminal and self._valid:
            self._start()

    def _stop(self) -> None:
        self._generation += 1
        self.workers.cancel_group(self, "public-run-read")
        self._reading = False

    def _start(self) -> None:
        if self.run_id is None:
            self._clear()
            return
        self._stop()
        self._reading = True
        self.run_worker(
            self._follow(self._generation), group="public-run-read", exclusive=True
        )

    def _clear(self) -> None:
        self.records.clear()
        self.next_after = 0
        self.terminal = False
        self._summary.update("Public model summary unavailable.")
        self._trace.update("Execution trace unavailable. Press r to retry.")

    def invalidate(self) -> None:
        """Drop protected values when a later transport frame breaks the binding."""
        self._valid = False
        self._stop()
        self._clear()

    def revalidate(self) -> None:
        """Resume only after a fresh transport validates the exact stored binding."""
        if not self._valid:
            self._valid = True
            if not (self.summary_fold.collapsed and self.trace_fold.collapsed):
                self._start()

    def action_replay(self) -> None:
        if self._valid:
            self._stop()
            self._clear()
            if not (self.summary_fold.collapsed and self.trace_fold.collapsed):
                self._start()

    async def _follow(self, generation: int) -> None:
        try:
            while (
                generation == self._generation
                and self._valid
                and self.run_id is not None
                and not self.terminal
            ):
                after = self.next_after
                try:
                    value = await self.client.get_public_run_events(
                        self.run_id, task_id=self.task_id, after=after
                    )
                    page = PublicRunPage.parse(value, self.run_id, after)
                except (ArboraOperationError, ValueError):
                    if generation == self._generation:
                        self._clear()
                    return
                except Exception:
                    if generation != self._generation:
                        return
                    self._clear()
                    await asyncio.sleep(self.POLL_INTERVAL)
                    continue
                if generation != self._generation:
                    return
                if not self.apply_page(page):
                    return
                if not self.terminal:
                    await asyncio.sleep(0 if page.has_more else self.POLL_INTERVAL)
        finally:
            if generation == self._generation:
                self._reading = False

    def apply_page(self, page: PublicRunPage) -> bool:
        """Update mounted content, leaving the fold widgets and focus in place."""
        retained_ids = {event.event_id for event in self.records}
        if page.events and (
            self.terminal
            or page.events[0].sequence != self.next_after + 1
            or any(event.event_id in retained_ids for event in page.events)
        ):
            self._clear()
            return False
        self.records.extend(page.events)
        self.records = self.records[-MAX_EVENTS:]
        retained_bytes = sum(len(event.text.encode()) for event in self.records)
        while self.records and retained_bytes > MAX_VIEW_BYTES:
            retained_bytes -= len(self.records.pop(0).text.encode())
        self.next_after, self.terminal = page.next_after, page.terminal
        summaries = [
            event.summary for event in self.records if event.summary is not None
        ]
        traces = [event.text for event in self.records if event.summary is None]
        self._summary.update(
            "\n\n".join(summaries)
            or "Public model summary unavailable in the retained event window."
        )
        prefix = (
            "Earlier events omitted from this bounded view.\n"
            if self.records and self.records[0].sequence > 1
            else ""
        )
        self._trace.update(
            prefix
            + (
                "\n\n".join(traces)
                or "Execution trace unavailable: no execution records were supplied."
            )
        )

        return True

    def on_unmount(self) -> None:
        self._stop()
        self._clear()
