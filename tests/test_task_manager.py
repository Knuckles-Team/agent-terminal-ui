"""Tests for task_manager.py -- Durable task queue."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from agent_terminal_ui.task_manager import TaskManager, TaskRecord


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_tasks.db"


@pytest.fixture
def tm(db_path: Path) -> Generator[TaskManager, None, None]:
    mgr = TaskManager(db_path=db_path, max_concurrent=3)
    yield mgr
    mgr.close()


class TestTaskCRUD:
    def test_create_task(self, tm: TaskManager) -> None:
        task = tm.create_task("Build feature", "Implement the widget")
        assert task.id
        assert task.title == "Build feature"
        assert task.status == "queued"

    def test_get_task(self, tm: TaskManager) -> None:
        task = tm.create_task("Test task")
        fetched = tm.get_task(task.id)
        assert fetched is not None
        assert fetched.title == "Test task"

    def test_get_task_not_found(self, tm: TaskManager) -> None:
        assert tm.get_task("nonexistent") is None

    def test_list_tasks(self, tm: TaskManager) -> None:
        tm.create_task("A")
        tm.create_task("B")
        tasks = tm.list_tasks()
        assert len(tasks) == 2

    def test_list_tasks_by_status(self, tm: TaskManager) -> None:
        tm.create_task("Queued")
        t2 = tm.create_task("Will Run")
        tm.start_task(t2.id)
        queued = tm.list_tasks(status="queued")
        running = tm.list_tasks(status="running")
        assert len(queued) == 1
        assert len(running) == 1


class TestTaskLifecycle:
    def test_start_task(self, tm: TaskManager) -> None:
        task = tm.create_task("Start me")
        assert tm.start_task(task.id) is True
        fetched = tm.get_task(task.id)
        assert fetched is not None
        assert fetched.status == "running"
        assert fetched.started_at > 0

    def test_complete_task(self, tm: TaskManager) -> None:
        task = tm.create_task("Complete me")
        tm.start_task(task.id)
        tm.complete_task(task.id, "All done")
        fetched = tm.get_task(task.id)
        assert fetched is not None
        assert fetched.status == "completed"
        assert fetched.result == "All done"

    def test_fail_task(self, tm: TaskManager) -> None:
        task = tm.create_task("Fail me")
        tm.start_task(task.id)
        tm.fail_task(task.id, "Something broke")
        fetched = tm.get_task(task.id)
        assert fetched is not None
        assert fetched.status == "failed"
        assert fetched.error == "Something broke"

    def test_cancel_task(self, tm: TaskManager) -> None:
        task = tm.create_task("Cancel me")
        tm.cancel_task(task.id)
        fetched = tm.get_task(task.id)
        assert fetched is not None
        assert fetched.status == "cancelled"

    def test_concurrency_cap(self, tm: TaskManager) -> None:
        tasks = [tm.create_task(f"Task {i}") for i in range(5)]
        assert tm.start_task(tasks[0].id) is True
        assert tm.start_task(tasks[1].id) is True
        assert tm.start_task(tasks[2].id) is True
        assert tm.start_task(tasks[3].id) is False  # cap reached


class TestTimeline:
    def test_timeline_events(self, tm: TaskManager) -> None:
        task = tm.create_task("Timeline test")
        tm.start_task(task.id)
        tm.complete_task(task.id)
        timeline = tm.get_timeline(task.id)
        assert len(timeline) >= 3  # created, started, completed
        event_types = [e.event_type for e in timeline]
        assert "created" in event_types
        assert "started" in event_types
        assert "completed" in event_types


class TestChecklist:
    def test_update_checklist(self, tm: TaskManager) -> None:
        task = tm.create_task("Checklist task")
        items = [
            {"label": "Step 1", "done": False},
            {"label": "Step 2", "done": True},
        ]
        tm.update_checklist(task.id, items)
        fetched = tm.get_task(task.id)
        assert fetched is not None
        assert len(fetched.checklist) == 2
        assert fetched.checklist[1]["done"] is True


class TestCrashRecovery:
    def test_recover_interrupted(self, tm: TaskManager) -> None:
        t1 = tm.create_task("Running 1")
        t2 = tm.create_task("Running 2")
        tm.start_task(t1.id)
        tm.start_task(t2.id)

        # Simulate crash recovery
        interrupted = tm.recover_interrupted()
        assert len(interrupted) == 2

        # Verify they are now marked as failed
        for t in interrupted:
            fetched = tm.get_task(t.id)
            assert fetched is not None
            assert fetched.status == "failed"
            assert "restart" in fetched.error.lower()


class TestTaskRecord:
    def test_is_terminal(self) -> None:
        record = TaskRecord(status="completed")
        assert record.is_terminal is True
        record.status = "running"
        assert record.is_terminal is False

    def test_to_dict(self) -> None:
        record = TaskRecord(title="Test", description="Desc")
        d = record.to_dict()
        assert d["title"] == "Test"
        assert "id" in d
