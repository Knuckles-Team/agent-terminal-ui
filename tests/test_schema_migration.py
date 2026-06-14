"""Tests for session manager schema v2 migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agent_terminal_ui.session_manager import SessionManager


class TestSchemaV2Migration:
    """Test automatic v1 -> v2 migration."""

    def test_new_db_creates_v2(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        mgr = SessionManager(db_path=db_path)
        conn = mgr._get_conn()

        # Check schema version
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        assert row["version"] == 2

    def test_new_db_has_v2_columns(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        mgr = SessionManager(db_path=db_path)
        conn = mgr._get_conn()

        # Verify new columns exist by inserting with them
        session = mgr.create_session(title="Test")
        conn.execute(
            "UPDATE sessions SET background = 1, needs_input = 0, "
            "last_response_preview = 'hello', goal_id = 'g1' WHERE id = ?",
            (session.id,),
        )
        conn.commit()

        row = conn.execute(
            "SELECT background, needs_input, last_response_preview, goal_id "
            "FROM sessions WHERE id = ?",
            (session.id,),
        ).fetchone()
        assert row["background"] == 1
        assert row["needs_input"] == 0
        assert row["last_response_preview"] == "hello"
        assert row["goal_id"] == "g1"

    def test_v1_db_migrates_to_v2(self, tmp_path: Path):
        db_path = tmp_path / "v1.db"

        # Create a v1 database manually
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL
            );
            INSERT INTO schema_version (version) VALUES (1);

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
                metadata_json TEXT DEFAULT '{}'
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
        """)
        conn.commit()

        # Insert a v1 session
        import time

        now = time.time()
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) "
            "VALUES ('s1', 'Old Session', ?, ?)",
            (now, now),
        )
        conn.commit()
        conn.close()

        # Now open with SessionManager - should auto-migrate
        mgr = SessionManager(db_path=db_path)
        conn = mgr._get_conn()

        # Verify version bumped
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        assert row["version"] == 2

        # Verify new columns exist on existing data
        row = conn.execute(
            "SELECT background, needs_input, last_response_preview, goal_id "
            "FROM sessions WHERE id = 's1'",
        ).fetchone()
        assert row["background"] == 0  # Default
        assert row["needs_input"] == 0  # Default
        assert row["last_response_preview"] == ""  # Default
        assert row["goal_id"] == ""  # Default

    def test_idempotent_migration(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        # Create twice - should not error
        mgr1 = SessionManager(db_path=db_path)
        mgr1.close()
        mgr2 = SessionManager(db_path=db_path)
        conn = mgr2._get_conn()
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        assert row["version"] == 2
