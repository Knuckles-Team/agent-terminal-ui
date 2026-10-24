"""Keyboard-accessible flat execution inspection, not an agent scheduler."""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static

from agent_terminal_ui.client import AgentClient
from agent_terminal_ui.display_text import display_text
from agent_terminal_ui.execution_graph import ExecutionGraph


class ExecutionGraphScreen(ModalScreen[None]):
    """Read a bounded run graph without changing the conversation target."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("r", "refresh_graph", "Refresh"),
        Binding("escape", "close", "Close"),
    ]

    DEFAULT_CSS = """
    ExecutionGraphScreen { align: center middle; }
    #execution-dialog {
        width: 100%; height: 100%; max-width: 120;
        background: $surface; border: thick $primary;
    }
    #execution-title { height: 1; text-style: bold; }
    #execution-status { height: auto; }
    #execution-nodes { height: 1fr; min-height: 4; }
    #execution-records { height: 1fr; min-height: 4; }
    #execution-detail, #execution-edges { height: auto; }
    #execution-actions { height: 3; }
    """

    def __init__(
        self,
        client: AgentClient,
        run_id: str,
        *,
        context_id: str | None,
        task_id: str | None = None,
    ) -> None:
        super().__init__()
        self.client, self.run_id, self.task_id = client, run_id, task_id
        self.graph: ExecutionGraph | None = None
        self.selected_key: str | None = None
        self._owner_context = context_id
        self._owner_scope = client.read_scope
        self._invalidated = False
        self._generation = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="execution-dialog"):
            yield Static("Execution graph (read-only)", id="execution-title")
            yield Static(
                "Reading authorized graph...", id="execution-status", markup=False
            )
            yield DataTable(id="execution-nodes", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="execution-records"):
                yield Static(
                    "Details unavailable.", id="execution-detail", markup=False
                )
                yield Static("", id="execution-edges", markup=False)
            with Horizontal(id="execution-actions"):
                yield Button("Refresh (R)", id="execution-refresh")
                yield Button("Close (Esc)", id="execution-close")

    def on_mount(self) -> None:
        self.query_one("#execution-nodes", DataTable).add_columns(
            "Plan step", "Observed state"
        )
        self.action_refresh_graph()
        self.query_one("#execution-nodes", DataTable).focus()

    def _same_owner(self) -> bool:
        return (
            not self._invalidated
            and getattr(self.app, "agent_client", self.client) is self.client
            and getattr(self.app, "current_session_id", None) == self._owner_context
            and self.client.read_scope == self._owner_scope
        )

    def _clear_protected(self, *, render: bool = True) -> None:
        self.graph = None
        self.selected_key = None
        if render:
            self.query_one("#execution-nodes", DataTable).clear()
            self.query_one("#execution-detail", Static).update("Details unavailable.")
            self.query_one("#execution-edges", Static).update("")

    def _stop(self) -> None:
        self._generation += 1
        self.workers.cancel_group(self, "execution-graph")

    def _owner_lost(self) -> None:
        if self._invalidated:
            return
        self._invalidated = True
        self._stop()
        self._clear_protected()
        self.query_one("#execution-status", Static).update(
            "Graph unavailable: connection or context changed. Close and reopen."
        )
        self.query_one("#execution-refresh", Button).disabled = True

    def on_idle(self) -> None:
        if self.is_mounted and not self._same_owner():
            self._owner_lost()

    def _current(self, generation: int) -> bool:
        if not self.is_mounted or generation != self._generation:
            return False
        if not self._same_owner():
            self._owner_lost()
            return False
        return True

    def action_refresh_graph(self) -> None:
        self._stop()
        self._clear_protected()
        if not self._same_owner():
            self._owner_lost()
            return
        self.query_one("#execution-status", Static).update(
            "Reading authorized graph..."
        )
        self.run_worker(
            self._read_graph(self._generation), group="execution-graph", exclusive=True
        )

    async def _read_graph(self, generation: int) -> None:
        if not self._current(generation):
            return
        try:
            graph = await self.client.get_execution_graph(
                self.run_id, task_id=self.task_id
            )
        except Exception:
            if self._current(generation):
                self._clear_protected()
                self.query_one("#execution-status", Static).update(
                    "Graph unavailable: unsupported, refused or invalid "
                    "runs.execution_graph read. R retries; no fallback is used."
                )
            return
        if not self._current(generation):
            return
        self.task_id = graph.task_id
        self.graph = graph
        self.query_one("#execution-status", Static).update(
            f"{len(graph.nodes)} steps / {len(graph.edges)} dependencies. "
            "Topology complete.\nLifecycle incomplete: observed prefix only, "
            f"cursor {graph.covered_after}; "
            f"more events: {'yes' if graph.has_more else 'no'}."
        )
        table = self.query_one("#execution-nodes", DataTable)
        for node in graph.nodes:
            table.add_row(
                Text(display_text(node.task_id, multiline=False)),
                Text(node.status),
                key=node.key,
            )
        table.move_cursor(row=0)
        self._select_node(graph.nodes[0].key)

    def _select_node(self, key: str) -> None:
        self.selected_key = None
        self.query_one("#execution-detail", Static).update("Details unavailable.")
        self.query_one("#execution-edges", Static).update("")
        if not self._current(self._generation) or self.graph is None:
            return
        graph = self.graph
        node = next((node for node in graph.nodes if node.key == key), None)
        if node is None:
            return
        self.selected_key = node.key
        evidence = (
            f"Public evidence: {display_text(node.event_id, multiline=False)} "
            f"/ sequence {node.sequence}"
            if node.event_id is not None
            else "No lifecycle event observed in this prefix."
        )
        self.query_one("#execution-detail", Static).update(
            display_text(
                f"Run: {display_text(graph.run_id, multiline=False)}\n"
                f"Root task: {display_text(graph.task_id, multiline=False)}\n"
                f"Plan digest: {display_text(graph.plan_digest, multiline=False)}\n"
                f"Plan step: {display_text(node.task_id, multiline=False)}\n"
                f"Key: {node.key}\nObserved state: {node.status}\n{evidence}\n"
                "Plan steps are not spawned child agents.\n"
                "Transcript, child messaging and continuation: unavailable."
            )
        )
        labels = {
            item.key: display_text(item.task_id, multiline=False)
            for item in graph.nodes
        }
        incoming = [labels[source] for source, target in graph.edges if target == key]
        outgoing = [labels[target] for source, target in graph.edges if source == key]
        edges = "\n".join(
            f"{labels[source]} -> {labels[target]}" for source, target in graph.edges
        )
        self.query_one("#execution-edges", Static).update(
            display_text(
                f"Predecessors: {', '.join(incoming) or 'none'}\n"
                f"Dependents: {', '.join(outgoing) or 'none'}\n"
                f"All depends_on edges (predecessor -> dependent):\n{edges or 'none'}"
            )
        )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "execution-nodes" and event.row_key.value is not None:
            self._select_node(event.row_key.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "execution-refresh":
            self.action_refresh_graph()
        elif event.button.id == "execution-close":
            self.action_close()

    def action_close(self) -> None:
        self._stop()
        self._clear_protected()
        self.dismiss()

    def on_unmount(self) -> None:
        self._stop()
        self._clear_protected(render=False)
