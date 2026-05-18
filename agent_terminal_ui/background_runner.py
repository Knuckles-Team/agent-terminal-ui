"""Background agent runner for detached sessions.

Manages agent sessions that run as async workers within the TUI
process. Each background session persists state through the
TaskManager for crash recovery.

Concept: TUI-21 (Background Agents)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BackgroundSession:
    """Tracks a single background agent session."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    status: str = "running"  # running | waiting | done | failed | cancelled
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_response: str = ""
    needs_input: bool = False
    goal_id: str = ""
    iteration: int = 0
    max_iterations: int = 20
    error: str = ""
    task: asyncio.Task[Any] | None = field(default=None, repr=False)


class BackgroundAgentRunner:
    """Manages detached agent sessions as async workers.

    Each background session gets its own async task. Workers
    persist state for crash recovery. Output is buffered and
    available for peek via the Agent View.

    Concept: TUI-21 (Background Agents)
    """

    def __init__(self, max_concurrent: int = 10) -> None:
        self._sessions: dict[str, BackgroundSession] = {}
        self._max_concurrent = max_concurrent

    @property
    def sessions(self) -> dict[str, BackgroundSession]:
        """All tracked background sessions."""
        return self._sessions

    def get_session(self, session_id: str) -> BackgroundSession | None:
        return self._sessions.get(session_id)

    def list_sessions(self, status: str | None = None) -> list[BackgroundSession]:
        sessions = list(self._sessions.values())
        if status:
            sessions = [s for s in sessions if s.status == status]
        return sorted(sessions, key=lambda s: s.updated_at, reverse=True)

    def create_session(
        self,
        title: str = "",
        goal_id: str = "",
        max_iterations: int = 20,
    ) -> BackgroundSession:
        """Create a new background session.

        Args:
            title: Human-readable session title.
            goal_id: Optional goal ID if this is a goal session.
            max_iterations: Max iterations for goal sessions.

        Returns:
            The created BackgroundSession.
        """
        running = sum(1 for s in self._sessions.values() if s.status == "running")
        if running >= self._max_concurrent:
            raise RuntimeError(
                f"Max concurrent sessions reached ({self._max_concurrent})"
            )

        session = BackgroundSession(
            title=title or f"Session {len(self._sessions) + 1}",
            goal_id=goal_id,
            max_iterations=max_iterations,
        )
        self._sessions[session.id] = session
        logger.info(f"Created background session: {session.id} ({session.title})")
        return session

    def update_session(
        self,
        session_id: str,
        status: str | None = None,
        last_response: str | None = None,
        needs_input: bool | None = None,
        iteration: int | None = None,
        error: str | None = None,
    ) -> None:
        """Update a background session's state.

        Args:
            session_id: Session to update.
            status: New status.
            last_response: Latest response preview.
            needs_input: Whether the session needs user input.
            iteration: Current iteration number.
            error: Error message if failed.
        """
        session = self._sessions.get(session_id)
        if not session:
            return

        if status is not None:
            session.status = status
        if last_response is not None:
            session.last_response = last_response
        if needs_input is not None:
            session.needs_input = needs_input
        if iteration is not None:
            session.iteration = iteration
        if error is not None:
            session.error = error
        session.updated_at = time.time()

    def cancel_session(self, session_id: str) -> bool:
        """Cancel a running background session.

        Args:
            session_id: Session to cancel.

        Returns:
            True if the session was cancelled.
        """
        session = self._sessions.get(session_id)
        if not session or session.status not in ("running", "waiting"):
            return False

        if session.task and not session.task.done():
            session.task.cancel()

        session.status = "cancelled"
        session.updated_at = time.time()
        logger.info(f"Cancelled background session: {session_id}")
        return True

    def remove_session(self, session_id: str) -> bool:
        """Remove a completed/failed session.

        Args:
            session_id: Session to remove.

        Returns:
            True if the session was removed.
        """
        session = self._sessions.get(session_id)
        if not session:
            return False

        if session.status == "running":
            self.cancel_session(session_id)

        del self._sessions[session_id]
        return True

    def get_summary(self) -> dict[str, int]:
        """Get a summary of all background sessions."""
        counts: dict[str, int] = {"total": len(self._sessions)}
        for session in self._sessions.values():
            counts[session.status] = counts.get(session.status, 0) + 1
        return counts

    def recover_interrupted(self) -> list[BackgroundSession]:
        """Mark running sessions as failed after a restart."""
        interrupted = []
        for session in self._sessions.values():
            if session.status == "running":
                session.status = "failed"
                session.error = "Interrupted by process restart"
                session.updated_at = time.time()
                interrupted.append(session)
        return interrupted
