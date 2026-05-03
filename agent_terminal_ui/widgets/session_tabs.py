"""Session tabs widget for multi-session management.

Provides a tab bar for switching between concurrent agent sessions,
each with its own Conversation state.

Concept: AU-018 (Session Management)
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import HorizontalGroup
from textual.message import Message
from textual.reactive import var
from textual.widgets import Static


class SessionTab(Static):
    """A single session tab."""

    DEFAULT_CSS = """
    SessionTab {
        height: 1;
        padding: 0 2;
        color: $text-muted;
        background: $surface;
        border-right: solid $primary 20%;
    }

    SessionTab:hover {
        background: $primary 20%;
    }

    SessionTab.-active {
        color: $primary;
        text-style: bold;
        background: $background;
        border-bottom: solid $primary;
    }
    """

    def __init__(
        self,
        session_id: str,
        label: str = "",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize a session tab.

        Args:
            session_id: Unique session identifier.
            label: Display label for the tab.
            name: Optional Textual name.
            id: Optional Textual id.
            classes: Optional Textual CSS classes.
        """
        super().__init__(label or session_id[:8], name=name, id=id, classes=classes)
        self.session_id = session_id


class SessionTabs(HorizontalGroup):
    """Tab bar for managing multiple concurrent sessions.

    Supports tab switching via keyboard shortcuts and click,
    with visual indicators for active/inactive sessions.
    """

    DEFAULT_CSS = """
    SessionTabs {
        height: 1;
        width: 100%;
        background: $surface;
        border-bottom: solid $primary 20%;
    }
    """

    class SessionSelected(Message):
        """Posted when a session tab is selected."""

        def __init__(self, session_id: str) -> None:
            self.session_id = session_id
            super().__init__()

    class SessionCreated(Message):
        """Posted when a new session is requested."""

        pass

    active_session: var[str] = var("")

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+left_square_bracket", "previous_session", "Previous"),
        Binding("ctrl+right_square_bracket", "next_session", "Next"),
    ]

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the session tabs."""
        super().__init__(name=name, id=id, classes=classes)
        self._sessions: list[str] = []

    def compose(self) -> ComposeResult:
        """Compose initial layout — starts with one default session."""
        yield Static("+ New", id="new-session-btn", classes="session-new-btn")

    async def add_session(self, session_id: str, label: str = "") -> None:
        """Add a new session tab.

        Args:
            session_id: Unique session identifier.
            label: Display label.
        """
        self._sessions.append(session_id)
        tab = SessionTab(session_id, label or f"Session {len(self._sessions)}")
        await self.mount(tab, before=self.query_one("#new-session-btn"))
        self.active_session = session_id
        self._update_active()

    def watch_active_session(self) -> None:
        """Update visual state when active session changes."""
        self._update_active()

    def _update_active(self) -> None:
        """Update the active tab visual state."""
        for tab in self.query(SessionTab):
            tab.set_class(tab.session_id == self.active_session, "-active")

    def action_previous_session(self) -> None:
        """Switch to the previous session."""
        if not self._sessions:
            return
        idx = (
            self._sessions.index(self.active_session)
            if self.active_session in self._sessions
            else 0
        )
        new_idx = (idx - 1) % len(self._sessions)
        self.active_session = self._sessions[new_idx]
        self.post_message(self.SessionSelected(self.active_session))

    def action_next_session(self) -> None:
        """Switch to the next session."""
        if not self._sessions:
            return
        idx = (
            self._sessions.index(self.active_session)
            if self.active_session in self._sessions
            else 0
        )
        new_idx = (idx + 1) % len(self._sessions)
        self.active_session = self._sessions[new_idx]
        self.post_message(self.SessionSelected(self.active_session))

    def on_click(self, event) -> None:
        """Handle tab clicks."""
        target = event.widget
        if isinstance(target, SessionTab):
            self.active_session = target.session_id
            self.post_message(self.SessionSelected(self.active_session))
        elif hasattr(target, "id") and target.id == "new-session-btn":
            self.post_message(self.SessionCreated())
