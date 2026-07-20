"""SQLite-backed session persistence with crash recovery.

Provides durable session storage, turn tracking, checkpoint/restore
lifecycle, and an offline queue that survives process restarts.
Integrates with the existing Knowledge Graph backend for chat
history while maintaining a local SQLite store for fast
session metadata and crash-recovery checkpoints.

Concept: TUI-1 (Session Persistence)
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


SCHEMA_VERSION = 2
DEFAULT_DB_PATH = get_shared_db_path("agent_terminal_ui.db")
DEFAULT_DB_DIR = DEFAULT_DB_PATH.parent


@dataclass
class SessionRecord:
    """A durable session record."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    model: str = ""
    mode: str = "ask"
    workspace: str = ""
    turn_count: int = 0
    status: str = "active"
    background: bool = False
    needs_input: bool = False
    last_response_preview: str = ""
    goal_id: str = ""  # active | completed | archived
    metadata_json: str = "{}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> SessionRecord:
        """Construct from a database row."""
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class TurnRecord:
    """A single turn within a session."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    turn_number: int = 0
    role: str = "user"  # user | assistant | system
    content: str = ""
    created_at: float = field(default_factory=time.time)
    status: str = "completed"  # queued | in_progress | completed | failed | interrupted
    usage_json: str = "{}"
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TurnRecord:
        """Construct from a database row."""
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class CheckpointRecord:
    """A pre-turn checkpoint for crash recovery."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    turn_number: int = 0
    created_at: float = field(default_factory=time.time)
    query: str = ""
    parts_json: str = "[]"
    mode: str = "ask"
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> CheckpointRecord:
        """Construct from a database row."""
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class OfflineQueueItem:
    """A queued message that survives process restarts."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    message: str = ""
    parts_json: str = "[]"
    mode: str = "ask"
    model: str = ""
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending | processing | completed | failed

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> OfflineQueueItem:
        """Construct from a database row."""
        return cls(**{k: row[k] for k in row.keys()})


class SessionManager:
    """SQLite-backed session persistence manager.

    Provides session CRUD, turn tracking, checkpoint/restore for crash
    recovery, and a durable offline queue. The database is stored globally
    at ``~/.config/agent-terminal-ui/agent_terminal_ui.db``.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize the session manager.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create the database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        """Initialize the database schema."""
        conn = self._get_conn()

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                model TEXT DEFAULT '',
                mode TEXT DEFAULT 'ask',
                workspace TEXT DEFAULT '',
                turn_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                metadata_json TEXT DEFAULT '{}',
                background INTEGER DEFAULT 0,
                needs_input INTEGER DEFAULT 0,
                last_response_preview TEXT DEFAULT '',
                goal_id TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS turns (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                turn_number INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                content TEXT DEFAULT '',
                created_at REAL NOT NULL,
                status TEXT DEFAULT 'completed',
                usage_json TEXT DEFAULT '{}',
                duration_ms INTEGER DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS checkpoints (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                turn_number INTEGER NOT NULL,
                created_at REAL NOT NULL,
                query TEXT DEFAULT '',
                parts_json TEXT DEFAULT '[]',
                mode TEXT DEFAULT 'ask',
                model TEXT DEFAULT '',
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS offline_queue (
                id TEXT PRIMARY KEY,
                session_id TEXT DEFAULT '',
                message TEXT NOT NULL,
                parts_json TEXT DEFAULT '[]',
                mode TEXT DEFAULT 'ask',
                model TEXT DEFAULT '',
                created_at REAL NOT NULL,
                status TEXT DEFAULT 'pending'
            );

            CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
            CREATE INDEX IF NOT EXISTS idx_checkpoints_session
                ON checkpoints(session_id);
            CREATE INDEX IF NOT EXISTS idx_offline_queue_status
                ON offline_queue(status);
        """)

        # Check/set schema version
        cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cursor.fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )
        else:
            current = row["version"]
            if current > SCHEMA_VERSION:
                msg = (
                    f"Database schema version {current} is newer than "
                    f"supported version {SCHEMA_VERSION}. Please upgrade."
                )
                raise RuntimeError(msg)
            if current < 2:
                self._migrate_v1_to_v2(conn)
                conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))

        conn.commit()

    def _migrate_v1_to_v2(self, conn: sqlite3.Connection) -> None:
        """Migrate schema from v1 to v2.

        Adds columns needed by Agent View (TUI-20) and /goal (ORCH-5.0):
        - background: whether session is running in background
        - needs_input: whether session is waiting for user input
        - last_response_preview: truncated last assistant response
        - goal_id: linked GoalNode ID for goal sessions
        """
        migrations = [
            "ALTER TABLE sessions ADD COLUMN background INTEGER DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN needs_input INTEGER DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN last_response_preview TEXT DEFAULT ''",
            "ALTER TABLE sessions ADD COLUMN goal_id TEXT DEFAULT ''",
        ]
        for sql in migrations:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # Column already exists
        logger.info("SessionManager: Migrated schema from v1 to v2")

    # -- Session CRUD --

    def create_session(
        self,
        title: str = "",
        model: str = "",
        mode: str = "ask",
        workspace: str = "",
    ) -> SessionRecord:
        """Create a new session.

        Args:
            title: Human-readable session title.
            model: The LLM model identifier.
            mode: The interaction mode.
            workspace: The workspace directory path.

        Returns:
            The created session record.
        """
        now = time.time()
        record = SessionRecord(
            title=title,
            created_at=now,
            updated_at=now,
            model=model,
            mode=mode,
            workspace=workspace,
        )
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO sessions
               (id, title, created_at, updated_at, model, mode, workspace,
                turn_count, status, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.title,
                record.created_at,
                record.updated_at,
                record.model,
                record.mode,
                record.workspace,
                record.turn_count,
                record.status,
                record.metadata_json,
            ),
        )
        conn.commit()
        return record

    def get_session(self, session_id: str) -> SessionRecord | None:
        """Fetch a session by ID.

        Args:
            session_id: The session identifier.

        Returns:
            The session record or None if not found.
        """
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return SessionRecord.from_row(row)

    def list_sessions(
        self,
        limit: int = 50,
        status: str | None = None,
        search: str | None = None,
    ) -> list[SessionRecord]:
        """List sessions, optionally filtered.

        Args:
            limit: Maximum number of sessions to return.
            status: Optional status filter (active, completed, archived).
            search: Optional search substring for title.

        Returns:
            List of matching session records.
        """
        conn = self._get_conn()
        query = "SELECT * FROM sessions"
        params: list[Any] = []
        conditions: list[str] = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if search:
            conditions.append("title LIKE ?")
            params.append(f"%{search}%")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        return [SessionRecord.from_row(row) for row in cursor.fetchall()]

    def update_session(self, session_id: str, **kwargs: Any) -> None:
        """Update session fields.

        Args:
            session_id: The session to update.
            **kwargs: Fields to update (title, model, mode, status, etc.).
        """
        allowed = {
            "title",
            "model",
            "mode",
            "status",
            "turn_count",
            "metadata_json",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return

        updates["updated_at"] = time.time()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [session_id]

        conn = self._get_conn()
        conn.execute(
            f"UPDATE sessions SET {set_clause} WHERE id = ?",  # nosec B608
            values,
        )
        conn.commit()

    def archive_session(self, session_id: str) -> None:
        """Archive a session.

        Args:
            session_id: The session to archive.
        """
        self.update_session(session_id, status="archived")

    def delete_session(self, session_id: str) -> None:
        """Delete a session and all associated data.

        Args:
            session_id: The session to delete.
        """
        conn = self._get_conn()
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()

    def fork_session(
        self, session_id: str, at_turn: int | None = None
    ) -> SessionRecord:
        """Fork a session at a given turn, creating a new branch.

        Args:
            session_id: The source session to fork.
            at_turn: Optional turn number to fork at (defaults to latest).

        Returns:
            The newly created forked session.
        """
        original = self.get_session(session_id)
        if original is None:
            msg = f"Session {session_id} not found"
            raise ValueError(msg)

        new_session = self.create_session(
            title=f"Fork of {original.title or original.id[:8]}",
            model=original.model,
            mode=original.mode,
            workspace=original.workspace,
        )

        # Copy turns up to the fork point
        conn = self._get_conn()
        query = "SELECT * FROM turns WHERE session_id = ?"
        params: list[Any] = [session_id]
        if at_turn is not None:
            query += " AND turn_number <= ?"
            params.append(at_turn)
        query += " ORDER BY turn_number"

        cursor = conn.execute(query, params)
        for row in cursor.fetchall():
            turn = TurnRecord.from_row(row)
            new_turn = TurnRecord(
                session_id=new_session.id,
                turn_number=turn.turn_number,
                role=turn.role,
                content=turn.content,
                created_at=turn.created_at,
                status=turn.status,
                usage_json=turn.usage_json,
                duration_ms=turn.duration_ms,
            )
            conn.execute(
                """INSERT INTO turns
                   (id, session_id, turn_number, role, content, created_at,
                    status, usage_json, duration_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_turn.id,
                    new_turn.session_id,
                    new_turn.turn_number,
                    new_turn.role,
                    new_turn.content,
                    new_turn.created_at,
                    new_turn.status,
                    new_turn.usage_json,
                    new_turn.duration_ms,
                ),
            )

        conn.commit()
        return new_session

    # -- Turn tracking --

    def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        usage: dict[str, Any] | None = None,
        duration_ms: int = 0,
    ) -> TurnRecord:
        """Record a turn in a session.

        Args:
            session_id: The session to add the turn to.
            role: The role (user, assistant, system).
            content: The turn content.
            usage: Optional token usage data.
            duration_ms: Turn duration in milliseconds.

        Returns:
            The created turn record.
        """
        conn = self._get_conn()

        # Get next turn number
        cursor = conn.execute(
            "SELECT COALESCE(MAX(turn_number), 0) + 1 FROM turns WHERE session_id = ?",
            (session_id,),
        )
        next_turn = cursor.fetchone()[0]

        record = TurnRecord(
            session_id=session_id,
            turn_number=next_turn,
            role=role,
            content=content,
            usage_json=json.dumps(usage or {}),
            duration_ms=duration_ms,
        )

        conn.execute(
            """INSERT INTO turns
               (id, session_id, turn_number, role, content, created_at,
                status, usage_json, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.session_id,
                record.turn_number,
                record.role,
                record.content,
                record.created_at,
                record.status,
                record.usage_json,
                record.duration_ms,
            ),
        )

        # Update session turn count and timestamp
        conn.execute(
            "UPDATE sessions SET turn_count = ?, updated_at = ? WHERE id = ?",
            (next_turn, time.time(), session_id),
        )
        conn.commit()
        return record

    def get_turns(self, session_id: str, limit: int = 100) -> list[TurnRecord]:
        """Get turns for a session.

        Args:
            session_id: The session to fetch turns for.
            limit: Maximum number of turns to return.

        Returns:
            List of turn records ordered by turn number.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM turns WHERE session_id = ? ORDER BY turn_number LIMIT ?",
            (session_id, limit),
        )
        return [TurnRecord.from_row(row) for row in cursor.fetchall()]

    # -- Checkpoint/crash recovery --

    def write_checkpoint(
        self,
        session_id: str,
        turn_number: int,
        query: str,
        parts: list[dict[str, Any]] | None = None,
        mode: str = "ask",
        model: str = "",
    ) -> CheckpointRecord:
        """Write a pre-turn checkpoint for crash recovery.

        Args:
            session_id: The session being checkpointed.
            turn_number: The turn about to start.
            query: The user query.
            parts: Optional multi-modal parts.
            mode: The interaction mode.
            model: The model identifier.

        Returns:
            The checkpoint record.
        """
        conn = self._get_conn()

        # Remove any previous checkpoint for this session
        conn.execute("DELETE FROM checkpoints WHERE session_id = ?", (session_id,))

        record = CheckpointRecord(
            session_id=session_id,
            turn_number=turn_number,
            query=query,
            parts_json=json.dumps(parts or []),
            mode=mode,
            model=model,
        )

        conn.execute(
            """INSERT INTO checkpoints
               (id, session_id, turn_number, created_at, query,
                parts_json, mode, model)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.session_id,
                record.turn_number,
                record.created_at,
                record.query,
                record.parts_json,
                record.mode,
                record.model,
            ),
        )
        conn.commit()
        return record

    def get_checkpoint(self, session_id: str) -> CheckpointRecord | None:
        """Get the latest checkpoint for a session.

        Args:
            session_id: The session to look up.

        Returns:
            The checkpoint record or None.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM checkpoints WHERE session_id = ? ORDER BY created_at DESC "
            "LIMIT 1",
            (session_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return CheckpointRecord.from_row(row)

    def clear_checkpoint(self, session_id: str) -> None:
        """Clear checkpoints after a successful turn.

        Args:
            session_id: The session whose checkpoints to clear.
        """
        conn = self._get_conn()
        conn.execute("DELETE FROM checkpoints WHERE session_id = ?", (session_id,))
        conn.commit()

    def recover_interrupted_turns(self) -> list[CheckpointRecord]:
        """Find all uncleared checkpoints (potential crash recovery targets).

        Returns:
            List of checkpoint records from sessions that may need recovery.
        """
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM checkpoints ORDER BY created_at DESC")
        return [CheckpointRecord.from_row(row) for row in cursor.fetchall()]

    # -- Offline queue --

    def enqueue_offline(
        self,
        message: str,
        session_id: str = "",
        parts: list[dict[str, Any]] | None = None,
        mode: str = "ask",
        model: str = "",
    ) -> OfflineQueueItem:
        """Add a message to the offline queue.

        Args:
            message: The user message to queue.
            session_id: Optional session to associate with.
            parts: Optional multi-modal parts.
            mode: The interaction mode.
            model: The model identifier.

        Returns:
            The created queue item.
        """
        item = OfflineQueueItem(
            session_id=session_id,
            message=message,
            parts_json=json.dumps(parts or []),
            mode=mode,
            model=model,
        )

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO offline_queue
               (id, session_id, message, parts_json, mode, model, created_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.id,
                item.session_id,
                item.message,
                item.parts_json,
                item.mode,
                item.model,
                item.created_at,
                item.status,
            ),
        )
        conn.commit()
        return item

    def dequeue_offline(self) -> OfflineQueueItem | None:
        """Pop the next pending item from the offline queue.

        Returns:
            The next pending queue item, or None if empty.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM offline_queue WHERE status = 'pending' "
            "ORDER BY created_at LIMIT 1"
        )
        row = cursor.fetchone()
        if row is None:
            return None

        item = OfflineQueueItem.from_row(row)
        conn.execute(
            "UPDATE offline_queue SET status = 'processing' WHERE id = ?", (item.id,)
        )
        conn.commit()
        item.status = "processing"
        return item

    def complete_offline(self, item_id: str, status: str = "completed") -> None:
        """Mark an offline queue item as completed or failed.

        Args:
            item_id: The queue item identifier.
            status: The completion status (completed or failed).
        """
        conn = self._get_conn()
        conn.execute(
            "UPDATE offline_queue SET status = ? WHERE id = ?", (status, item_id)
        )
        conn.commit()

    def list_offline_queue(self, status: str = "pending") -> list[OfflineQueueItem]:
        """List offline queue items by status.

        Args:
            status: The status to filter on.

        Returns:
            List of matching queue items.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM offline_queue WHERE status = ? ORDER BY created_at",
            (status,),
        )
        return [OfflineQueueItem.from_row(row) for row in cursor.fetchall()]

    def clear_offline_queue(self) -> int:
        """Clear all pending offline queue items.

        Returns:
            Number of items cleared.
        """
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM offline_queue WHERE status = 'pending'")
        conn.commit()
        return cursor.rowcount

    # -- Cleanup --

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
