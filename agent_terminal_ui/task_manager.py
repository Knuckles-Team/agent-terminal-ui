"""Durable background task queue with SQLite persistence.

Background tasks survive process restarts, support bounded-concurrency
worker pools, and track timeline events and artifacts.

Concept: TUI-5 (Durable Task Queue)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import os


def get_shared_db_path(db_filename: str) -> Path:
    """Resolve shared XDG path from agent-utilities data directory."""
    # 1. Check AGENT_UTILITIES_DATA_DIR environment variable
    override_data = os.environ.get("AGENT_UTILITIES_DATA_DIR")
    if override_data:
        return Path(override_data).expanduser() / db_filename

    # 2. Check AGENT_UTILITIES_CONFIG_DIR environment variable (as fallback config path)
    override_config = os.environ.get("AGENT_UTILITIES_CONFIG_DIR")
    if override_config:
        return (
            Path(override_config).expanduser().parent
            / "share"
            / "agent-utilities"
            / db_filename
        )

    # 3. Fallback to platformdirs standard XDG local share path for agent-utilities
    try:
        import platformdirs

        return (
            Path(platformdirs.user_data_path("agent-utilities", "knuckles-team"))
            / db_filename
        )
    except ImportError:
        return Path.home() / ".local" / "share" / "agent-utilities" / db_filename


DEFAULT_DB_PATH = get_shared_db_path("agent_terminal_ui.db")
DEFAULT_DB_DIR = DEFAULT_DB_PATH.parent


@dataclass
class TaskRecord:
    """A durable background task."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    status: str = "queued"  # queued | running | completed | failed | cancelled
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    session_id: str = ""
    command: str = ""
    result: str = ""
    error: str = ""
    metadata_json: str = "{}"
    checklist_json: str = "[]"
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TaskRecord:
        return cls(**{k: row[k] for k in row.keys()})

    @property
    def is_terminal(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")

    @property
    def duration_ms(self) -> int:
        if self.started_at == 0:
            return 0
        end = self.completed_at if self.completed_at > 0 else time.time()
        return int((end - self.started_at) * 1000)

    @property
    def checklist(self) -> list[dict[str, Any]]:
        return json.loads(self.checklist_json)

    def set_checklist(self, items: list[dict[str, Any]]) -> None:
        self.checklist_json = json.dumps(items)


@dataclass
class TimelineEvent:
    """A timeline event within a task."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    event_type: str = (
        ""  # started | progress | tool_call | artifact | completed | failed
    )
    message: str = ""
    created_at: float = field(default_factory=time.time)
    metadata_json: str = "{}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TimelineEvent:
        return cls(**{k: row[k] for k in row.keys()})


class TaskManager:
    """SQLite-backed durable task queue.

    Manages background tasks that survive restarts, with bounded
    concurrency, timeline tracking, and checklist state.
    """

    def __init__(self, db_path: Path | None = None, max_concurrent: int = 5) -> None:
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._max_concurrent = max_concurrent
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT DEFAULT '',
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'queued',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                started_at REAL DEFAULT 0.0,
                completed_at REAL DEFAULT 0.0,
                session_id TEXT DEFAULT '',
                command TEXT DEFAULT '',
                result TEXT DEFAULT '',
                error TEXT DEFAULT '',
                metadata_json TEXT DEFAULT '{}',
                checklist_json TEXT DEFAULT '[]',
                priority INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS task_timeline (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT DEFAULT '',
                created_at REAL NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_timeline_task ON task_timeline(task_id);
        """)
        conn.commit()

    def create_task(
        self,
        title: str,
        description: str = "",
        command: str = "",
        session_id: str = "",
        priority: int = 0,
    ) -> TaskRecord:
        """Create and enqueue a new task."""
        now = time.time()
        record = TaskRecord(
            title=title,
            description=description,
            command=command,
            session_id=session_id,
            priority=priority,
            created_at=now,
            updated_at=now,
        )
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO tasks (id, title, description, status, created_at, "
            "updated_at, started_at, completed_at, session_id, command, "
            "result, error, metadata_json, checklist_json, priority) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.title,
                record.description,
                record.status,
                record.created_at,
                record.updated_at,
                record.started_at,
                record.completed_at,
                record.session_id,
                record.command,
                record.result,
                record.error,
                record.metadata_json,
                record.checklist_json,
                record.priority,
            ),
        )
        self._add_timeline_event(record.id, "created", f"Task created: {title}")
        conn.commit()
        return record

    def get_task(self, task_id: str) -> TaskRecord | None:
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return TaskRecord.from_row(row) if row else None

    def list_tasks(
        self, status: str | None = None, limit: int = 50
    ) -> list[TaskRecord]:
        conn = self._get_conn()
        if status:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE status = ? "
                "ORDER BY priority DESC, created_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM tasks ORDER BY priority DESC, created_at DESC LIMIT ?",
                (limit,),
            )
        return [TaskRecord.from_row(row) for row in cursor.fetchall()]

    def start_task(self, task_id: str) -> bool:
        """Transition a queued task to running if concurrency allows."""
        running_count = len(self.list_tasks(status="running"))
        if running_count >= self._max_concurrent:
            logger.warning(f"Concurrency cap reached ({self._max_concurrent})")
            return False
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "UPDATE tasks SET status = 'running', started_at = ?, updated_at = ? "
            "WHERE id = ? AND status = 'queued'",
            (now, now, task_id),
        )
        self._add_timeline_event(task_id, "started", "Task started")
        conn.commit()
        return True

    def complete_task(self, task_id: str, result: str = "") -> None:
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "UPDATE tasks SET status = 'completed', completed_at = ?, "
            "updated_at = ?, result = ? WHERE id = ?",
            (now, now, result, task_id),
        )
        self._add_timeline_event(
            task_id, "completed", f"Task completed: {result[:100]}"
        )
        conn.commit()

    def fail_task(self, task_id: str, error: str = "") -> None:
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "UPDATE tasks SET status = 'failed', completed_at = ?, "
            "updated_at = ?, error = ? WHERE id = ?",
            (now, now, error, task_id),
        )
        self._add_timeline_event(task_id, "failed", f"Task failed: {error[:100]}")
        conn.commit()

    def cancel_task(self, task_id: str) -> None:
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "UPDATE tasks SET status = 'cancelled', completed_at = ?, "
            "updated_at = ? WHERE id = ? AND status IN ('queued', 'running')",
            (now, now, task_id),
        )
        self._add_timeline_event(task_id, "cancelled", "Task cancelled")
        conn.commit()

    def update_checklist(self, task_id: str, items: list[dict[str, Any]]) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE tasks SET checklist_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(items), time.time(), task_id),
        )
        conn.commit()

    def get_timeline(self, task_id: str) -> list[TimelineEvent]:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM task_timeline WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        )
        return [TimelineEvent.from_row(row) for row in cursor.fetchall()]

    def _add_timeline_event(
        self,
        task_id: str,
        event_type: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event = TimelineEvent(
            task_id=task_id,
            event_type=event_type,
            message=message,
            metadata_json=json.dumps(metadata or {}),
        )
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO task_timeline (id, task_id, event_type, message, "
            "created_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.id,
                event.task_id,
                event.event_type,
                event.message,
                event.created_at,
                event.metadata_json,
            ),
        )

    def recover_interrupted(self) -> list[TaskRecord]:
        """Mark running tasks as interrupted on startup (crash recovery)."""
        conn = self._get_conn()
        now = time.time()
        cursor = conn.execute("SELECT * FROM tasks WHERE status = 'running'")
        interrupted = [TaskRecord.from_row(row) for row in cursor.fetchall()]
        for task in interrupted:
            conn.execute(
                "UPDATE tasks SET status = 'failed', "
                "error = 'Interrupted by process restart', updated_at = ? "
                "WHERE id = ?",
                (now, task.id),
            )
            self._add_timeline_event(
                task.id, "interrupted", "Interrupted by process restart"
            )
        conn.commit()
        return interrupted

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
