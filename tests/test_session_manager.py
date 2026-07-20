"""Tests for session_manager.py -- SQLite-backed session persistence."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from agent_terminal_ui.session_manager import (
    CheckpointRecord,
    OfflineQueueItem,
    SessionManager,
    SessionRecord,
    TurnRecord,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def manager(db_path: Path) -> Generator[SessionManager, None, None]:
    mgr = SessionManager(db_path=db_path)
    yield mgr
    mgr.close()


class TestSessionCRUD:
    def test_create_session(self, manager: SessionManager) -> None:
        session = manager.create_session(title="Test", model="gpt-4o", mode="ask")
        assert session.id
        assert session.title == "Test"
        assert session.model == "gpt-4o"
        assert session.mode == "ask"
        assert session.status == "active"
        assert session.turn_count == 0

    def test_get_session(self, manager: SessionManager) -> None:
        session = manager.create_session(title="Lookup")
        fetched = manager.get_session(session.id)
        assert fetched is not None
        assert fetched.title == "Lookup"

    def test_get_session_not_found(self, manager: SessionManager) -> None:
        assert manager.get_session("nonexistent") is None

    def test_list_sessions(self, manager: SessionManager) -> None:
        manager.create_session(title="A")
        manager.create_session(title="B")
        manager.create_session(title="C")
        sessions = manager.list_sessions()
        assert len(sessions) == 3

    def test_list_sessions_with_status_filter(self, manager: SessionManager) -> None:
        s1 = manager.create_session(title="Active")
        s2 = manager.create_session(title="Archived")
        manager.archive_session(s2.id)
        active = manager.list_sessions(status="active")
        assert len(active) == 1
        assert active[0].id == s1.id

    def test_list_sessions_with_search(self, manager: SessionManager) -> None:
        manager.create_session(title="Python debugging")
        manager.create_session(title="Rust project")
        results = manager.list_sessions(search="Python")
        assert len(results) == 1
        assert results[0].title == "Python debugging"

    def test_update_session(self, manager: SessionManager) -> None:
        session = manager.create_session(title="Original")
        manager.update_session(session.id, title="Updated", model="claude-3")
        fetched = manager.get_session(session.id)
        assert fetched is not None
        assert fetched.title == "Updated"
        assert fetched.model == "claude-3"

    def test_archive_session(self, manager: SessionManager) -> None:
        session = manager.create_session()
        manager.archive_session(session.id)
        fetched = manager.get_session(session.id)
        assert fetched is not None
        assert fetched.status == "archived"

    def test_delete_session(self, manager: SessionManager) -> None:
        session = manager.create_session()
        manager.delete_session(session.id)
        assert manager.get_session(session.id) is None

    def test_fork_session(self, manager: SessionManager) -> None:
        session = manager.create_session(title="Source")
        manager.add_turn(session.id, "user", "Hello")
        manager.add_turn(session.id, "assistant", "Hi there")
        manager.add_turn(session.id, "user", "Question")

        forked = manager.fork_session(session.id, at_turn=2)
        assert forked.title.startswith("Fork of")
        forked_turns = manager.get_turns(forked.id)
        assert len(forked_turns) == 2

    def test_fork_session_not_found(self, manager: SessionManager) -> None:
        with pytest.raises(ValueError, match="not found"):
            manager.fork_session("nonexistent")


class TestTurnTracking:
    def test_add_turn(self, manager: SessionManager) -> None:
        session = manager.create_session()
        turn = manager.add_turn(session.id, "user", "Hello world")
        assert turn.session_id == session.id
        assert turn.turn_number == 1
        assert turn.role == "user"
        assert turn.content == "Hello world"

    def test_sequential_turn_numbers(self, manager: SessionManager) -> None:
        session = manager.create_session()
        t1 = manager.add_turn(session.id, "user", "First")
        t2 = manager.add_turn(session.id, "assistant", "Second")
        t3 = manager.add_turn(session.id, "user", "Third")
        assert t1.turn_number == 1
        assert t2.turn_number == 2
        assert t3.turn_number == 3

    def test_get_turns(self, manager: SessionManager) -> None:
        session = manager.create_session()
        manager.add_turn(session.id, "user", "A")
        manager.add_turn(session.id, "assistant", "B")
        turns = manager.get_turns(session.id)
        assert len(turns) == 2
        assert turns[0].content == "A"
        assert turns[1].content == "B"

    def test_turn_updates_session_count(self, manager: SessionManager) -> None:
        session = manager.create_session()
        manager.add_turn(session.id, "user", "Msg")
        manager.add_turn(session.id, "assistant", "Reply")
        updated = manager.get_session(session.id)
        assert updated is not None
        assert updated.turn_count == 2


class TestCheckpoints:
    def test_write_and_get_checkpoint(self, manager: SessionManager) -> None:
        session = manager.create_session()
        manager.write_checkpoint(session.id, 1, "My query", mode="plan")
        cp = manager.get_checkpoint(session.id)
        assert cp is not None
        assert cp.session_id == session.id
        assert cp.query == "My query"
        assert cp.mode == "plan"

    def test_clear_checkpoint(self, manager: SessionManager) -> None:
        session = manager.create_session()
        manager.write_checkpoint(session.id, 1, "test")
        manager.clear_checkpoint(session.id)
        assert manager.get_checkpoint(session.id) is None

    def test_checkpoint_replaces_previous(self, manager: SessionManager) -> None:
        session = manager.create_session()
        manager.write_checkpoint(session.id, 1, "first")
        manager.write_checkpoint(session.id, 2, "second")
        cp = manager.get_checkpoint(session.id)
        assert cp is not None
        assert cp.query == "second"
        assert cp.turn_number == 2

    def test_recover_interrupted_turns(self, manager: SessionManager) -> None:
        s1 = manager.create_session()
        s2 = manager.create_session()
        manager.write_checkpoint(s1.id, 1, "q1")
        manager.write_checkpoint(s2.id, 3, "q2")
        recovered = manager.recover_interrupted_turns()
        assert len(recovered) == 2


class TestOfflineQueue:
    def test_enqueue_and_dequeue(self, manager: SessionManager) -> None:
        manager.enqueue_offline("Hello", mode="ask")
        item = manager.dequeue_offline()
        assert item is not None
        assert item.message == "Hello"
        assert item.status == "processing"

    def test_dequeue_empty(self, manager: SessionManager) -> None:
        assert manager.dequeue_offline() is None

    def test_fifo_order(self, manager: SessionManager) -> None:
        manager.enqueue_offline("First")
        manager.enqueue_offline("Second")
        manager.enqueue_offline("Third")
        item = manager.dequeue_offline()
        assert item is not None
        assert item.message == "First"

    def test_complete_offline(self, manager: SessionManager) -> None:
        manager.enqueue_offline("Test")
        item = manager.dequeue_offline()
        assert item is not None
        manager.complete_offline(item.id, "completed")
        pending = manager.list_offline_queue("pending")
        assert len(pending) == 0

    def test_list_offline_queue(self, manager: SessionManager) -> None:
        manager.enqueue_offline("A")
        manager.enqueue_offline("B")
        pending = manager.list_offline_queue("pending")
        assert len(pending) == 2

    def test_clear_offline_queue(self, manager: SessionManager) -> None:
        manager.enqueue_offline("A")
        manager.enqueue_offline("B")
        cleared = manager.clear_offline_queue()
        assert cleared == 2
        assert len(manager.list_offline_queue()) == 0


class TestDataclassSerialization:
    def test_session_record_to_dict(self) -> None:
        record = SessionRecord(title="Test")
        d = record.to_dict()
        assert d["title"] == "Test"
        assert "id" in d

    def test_turn_record_to_dict(self) -> None:
        record = TurnRecord(role="user", content="Hello")
        d = record.to_dict()
        assert d["role"] == "user"

    def test_checkpoint_record_to_dict(self) -> None:
        record = CheckpointRecord(query="test query")
        d = record.to_dict()
        assert d["query"] == "test query"

    def test_offline_queue_item_to_dict(self) -> None:
        item = OfflineQueueItem(message="queued")
        d = item.to_dict()
        assert d["message"] == "queued"
        assert d["status"] == "pending"
