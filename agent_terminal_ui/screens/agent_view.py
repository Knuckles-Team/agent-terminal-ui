"""Agent View Screen — multi-session dashboard.

One place to manage all concurrent agent sessions. Kick off new agents,
send them to the background, and jump in only when needed.

Concept: TUI-20 (Agent View)
"""

from __future__ import annotations

import time
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Vertical
from textual.message import Message
from textual.reactive import var
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header, Label, Static


class AgentSessionRow:
    """In-memory representation of a session row."""

    def __init__(
        self,
        session_id: str,
        title: str = "",
        status: str = "working",
        last_response: str = "",
        last_activity: float = 0.0,
        needs_input: bool = False,
        background: bool = False,
        goal_id: str = "",
    ) -> None:
        self.session_id = session_id
        self.title = title or session_id[:8]
        self.status = status
        self.last_response = last_response
        self.last_activity = last_activity or time.time()
        self.needs_input = needs_input
        self.background = background
        self.goal_id = goal_id

    @property
    def status_icon(self) -> str:
        return {
            "working": "🟢",
            "waiting": "🟡",
            "done": "✅",
            "failed": "❌",
            "cancelled": "🚫",
        }.get(self.status, "❓")

    @property
    def elapsed_display(self) -> str:
        elapsed = time.time() - self.last_activity
        if elapsed < 60:
            return f"{int(elapsed)}s ago"
        elif elapsed < 3600:
            return f"{int(elapsed / 60)}m ago"
        return f"{int(elapsed / 3600)}h ago"

    @property
    def preview(self) -> str:
        text = self.last_response.replace("\n", " ").strip()
        return (text[:57] + "...") if len(text) > 60 else (text or "(no output yet)")


class PeekPanel(Container):
    """Detail panel showing the last turn of a selected session."""

    DEFAULT_CSS = """
    PeekPanel {
        height: 40%;
        border-top: solid $primary 50%;
        padding: 1 2;
        background: $surface;
    }
    PeekPanel #peek-title { text-style: bold; color: $primary; margin-bottom: 1; }
    PeekPanel #peek-content { height: 1fr; overflow-y: auto; color: $text; }
    PeekPanel #peek-hint { color: $text-muted; text-style: italic; dock: bottom; }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._session_id: str = ""

    def compose(self) -> ComposeResult:
        yield Label("No session selected", id="peek-title")
        yield Static("Select a session to peek.", id="peek-content")
        yield Label("[Enter] Attach  [r] Reply  [n] New  [d] Delete", id="peek-hint")

    def update_peek(
        self, session_id: str, title: str, content: str, needs_input: bool = False
    ) -> None:
        self._session_id = session_id
        self.query_one("#peek-title", Label).update(
            f"📋 {title}" + (" 🟡 Waiting" if needs_input else "")
        )
        self.query_one("#peek-content", Static).update(content or "(no output yet)")
        hint = "[Enter] Attach  [r] Reply  [n] New  [d] Delete"
        self.query_one("#peek-hint", Label).update(hint)


class AgentViewScreen(Screen):
    """Multi-session dashboard for managing concurrent agent sessions.

    Concept: TUI-20 (Agent View)
    """

    CSS = """
    AgentViewScreen { layout: vertical; }
    AgentViewScreen #session-list-container { height: 60%; }
    AgentViewScreen #agent-view-header {
        height: 3; padding: 0 2; background: $primary 15%;
        color: $primary; text-style: bold; content-align: center middle;
    }
    AgentViewScreen DataTable { height: 1fr; }
    AgentViewScreen #empty-state {
        height: 1fr; content-align: center middle;
        color: $text-muted; text-style: italic;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "attach_session", "Attach", show=True),
        Binding("n", "new_session", "New", show=True),
        Binding("d", "delete_session", "Delete", show=True),
        Binding("r", "reply_inline", "Reply", show=True),
        Binding("right", "attach_session", "→ Attach", show=False),
        Binding("escape", "go_back", "Back", show=True),
    ]

    class SessionAttachRequested(Message):
        def __init__(self, session_id: str) -> None:
            self.session_id = session_id
            super().__init__()

    class NewSessionRequested(Message):
        pass

    class SessionDeleteRequested(Message):
        def __init__(self, session_id: str) -> None:
            self.session_id = session_id
            super().__init__()

    selected_session: var[str] = var("")

    def __init__(self, sessions: list[AgentSessionRow] | None = None, **kw: Any):
        super().__init__(**kw)
        self._sessions: list[AgentSessionRow] = sessions or []
        self._refresh_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Container(id="session-list-container"):
                yield Label("🤖 Agent View — All Sessions", id="agent-view-header")
                if self._sessions:
                    yield DataTable(id="session-table", cursor_type="row")
                else:
                    yield Label(
                        "No active sessions. Press [n] to start.", id="empty-state"
                    )
            yield PeekPanel(id="peek-panel")
        yield Footer()

    def on_mount(self) -> None:
        try:
            table = self.query_one("#session-table", DataTable)
            table.add_columns("Status", "Title", "Last Response", "Active", "Type")
            self._populate_table()
        except Exception:  # nosec B110
            pass
        self._refresh_timer = self.set_interval(2.0, self._refresh_sessions)

    def _populate_table(self) -> None:
        try:
            table = self.query_one("#session-table", DataTable)
        except Exception:
            return
        table.clear()
        for s in self._sessions:
            stype = "🎯 Goal" if s.goal_id else "💬 Chat"
            table.add_row(
                s.status_icon,
                s.title,
                s.preview,
                s.elapsed_display,
                stype,
                key=s.session_id,
            )

    def _refresh_sessions(self) -> None:
        self._populate_table()

    def update_sessions(self, sessions: list[AgentSessionRow]) -> None:
        self._sessions = sessions
        self._populate_table()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is None:
            return
        sid = str(event.row_key.value)
        session = next((s for s in self._sessions if s.session_id == sid), None)
        if session:
            self.selected_session = sid
            self.query_one("#peek-panel", PeekPanel).update_peek(
                sid, session.title, session.last_response, session.needs_input
            )

    def action_attach_session(self) -> None:
        if self.selected_session:
            self.post_message(self.SessionAttachRequested(self.selected_session))

    def action_new_session(self) -> None:
        self.post_message(self.NewSessionRequested())

    def action_delete_session(self) -> None:
        if self.selected_session:
            self.post_message(self.SessionDeleteRequested(self.selected_session))

    def action_reply_inline(self) -> None:
        if self.selected_session:
            self.post_message(self.SessionAttachRequested(self.selected_session))

    def action_go_back(self) -> None:
        self.app.switch_mode("main")
