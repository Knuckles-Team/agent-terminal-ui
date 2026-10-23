"""Read-only browser for caller-owned A2A tasks and their served replies."""

from typing import Any

import httpx
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label, Static
from textual.worker import get_current_worker

from agent_terminal_ui.client import A2ATransportError, AgentClient


def task_reply(task: dict[str, Any]) -> str:
    """Render text artifacts only; absence is not an empty conversation."""
    artifacts = task.get("artifacts")
    if not isinstance(artifacts, list):
        return "Reply unavailable."
    texts: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or not isinstance(
            artifact.get("parts"), list
        ):
            return "Reply unavailable."
        for part in artifact["parts"]:
            if not isinstance(part, dict):
                return "Reply unavailable."
            if part.get("kind") == "text":
                if not isinstance(part.get("text"), str):
                    return "Reply unavailable."
                texts.append(part["text"])
    return "\n".join(texts) if any(texts) else "Reply unavailable."


class HistoryScreen(ModalScreen[None]):
    """Browse one task page at a time without resuming or submitting a turn."""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("n", "next_page", "Next page"),
        ("p", "previous_page", "Previous page"),
        ("r", "refresh_history", "Refresh"),
    ]
    DEFAULT_CSS = """
    HistoryScreen { align: center middle; }
    #history-dialog { width: 90%; height: 90%; border: thick $primary; padding: 1; }
    #history-table { height: 40%; }
    #history-reply-scroll { height: 1fr; }
    """

    def __init__(self, client: AgentClient, page: dict[str, Any]) -> None:
        super().__init__()
        self.client = client
        self.page = page
        self._page_cursors: list[str | None] = [None]
        self._reading = False

    def compose(self) -> ComposeResult:
        with Vertical(id="history-dialog"):
            yield Label("Task history (read-only)")
            yield Label("Task replies only. Prior user turns and resume unavailable.")
            yield DataTable(id="history-table")
            yield Label(
                "Enter: read reply | P: previous | N: next page | "
                "R: refresh | Esc: close",
                id="history-page",
            )
            with VerticalScroll(id="history-reply-scroll"):
                yield Static(
                    "Select a task to read its reply.", id="history-reply", markup=False
                )

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Updated", "Task", "Context", "State")
        table.cursor_type = "row"
        self._render_page()

    def _render_page(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        for task in self.page["tasks"]:
            table.add_row(
                Text(str(task["status"].get("timestamp") or "Unavailable")),
                Text(task["id"]),
                Text(task["contextId"]),
                Text(task["status"]["state"]),
            )
        self.query_one("#history-page", Label).update(
            "Enter: read reply | P: previous | N: next page | R: refresh | Esc: close"
            if self.page.get("nextCursor")
            else "Enter: read reply | P: previous | End of task list | "
            "R: refresh | Esc: close"
        )
        self.query_one("#history-reply", Static).update(
            "Select a task to read its reply."
            if self.page["tasks"]
            else "No tasks on this page."
        )

    @work(group="task-history")
    async def action_refresh_history(self) -> None:
        """Read the first server page again without retaining stale task details."""
        if self._reading:
            return
        worker = get_current_worker()
        self._reading = True
        self.page = {"tasks": [], "nextCursor": None}
        self._page_cursors = [None]
        self._render_page()
        reply = self.query_one("#history-reply", Static)
        reply.update("Refreshing task history...")
        self.query_one("#history-page", Label).update(
            "Refreshing task history | Esc: close"
        )
        try:
            page = await self.client.list_history_tasks()
            if worker.is_cancelled or not self.is_mounted:
                return
            self.page = page
            self._render_page()
        except (httpx.HTTPError, A2ATransportError, ValueError):
            if worker.is_cancelled or not self.is_mounted:
                return
            reply.update("Task history unavailable.")
            self.query_one("#history-page", Label).update(
                "R: retry refresh | Esc: close"
            )
        finally:
            self._reading = False

    @work(group="task-history")
    async def action_next_page(self) -> None:
        cursor = self.page.get("nextCursor")
        if self._reading or cursor is None:
            return
        if cursor in self._page_cursors:
            self.notify("Task history pagination unavailable.", severity="warning")
            return
        await self._read_page(cursor, [*self._page_cursors, cursor])

    @work(group="task-history")
    async def action_previous_page(self) -> None:
        """Reread the previous cursor without caching task content."""
        if self._reading or len(self._page_cursors) < 2:
            return
        path = self._page_cursors[:-1]
        await self._read_page(path[-1], path)

    async def _read_page(self, cursor: str | None, path: list[str | None]) -> None:
        worker = get_current_worker()
        self._reading = True
        # Preserve navigation for retry, but erase content before authorization.
        self.page = {"tasks": [], "nextCursor": self.page.get("nextCursor")}
        self._render_page()
        self.query_one("#history-reply", Static).update("Reading task page...")
        try:
            page = await self.client.list_history_tasks(cursor)
            if worker.is_cancelled or not self.is_mounted:
                return
            continuation = page.get("nextCursor")
            if continuation is not None and continuation in path:
                raise ValueError("Task history cursor repeated")
            self._page_cursors = path
            self.page = page
            self._render_page()
        except (httpx.HTTPError, A2ATransportError, ValueError):
            if worker.is_cancelled or not self.is_mounted:
                return
            self.query_one("#history-reply", Static).update("Task history unavailable.")
        finally:
            self._reading = False

    @work(group="task-history")
    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if self._reading or not 0 <= event.cursor_row < len(self.page["tasks"]):
            return
        selected = self.page["tasks"][event.cursor_row]
        self._reading = True
        reply = self.query_one("#history-reply", Static)
        reply.update("Reading task reply...")
        try:
            task = await self.client.get_history_task(
                selected["id"], selected["contextId"]
            )
            reply.update(task_reply(task))
        except (httpx.HTTPError, A2ATransportError, ValueError):
            reply.update("Task reply unavailable.")
        finally:
            self._reading = False

    def action_close(self) -> None:
        self.dismiss(None)
