"""Tests for shell.py JobCenter -- Shell job management."""

from __future__ import annotations

import pytest

from agent_terminal_ui.shell import JobCenter, JobRecord, ShellManager


class TestJobRecord:
    def test_initial_state(self) -> None:
        job = JobRecord("1", "ls -la", cwd="/tmp")
        assert job.status == "running"
        assert job.exit_code is None
        assert job.elapsed_ms >= 0

    def test_complete_success(self) -> None:
        job = JobRecord("1", "echo ok")
        job.complete(0)
        assert job.status == "completed"
        assert job.exit_code == 0
        assert job.completed_at is not None

    def test_complete_failure(self) -> None:
        job = JobRecord("1", "fail")
        job.complete(1)
        assert job.status == "failed"
        assert job.exit_code == 1

    def test_cancel(self) -> None:
        job = JobRecord("1", "long task")
        job.cancel()
        assert job.status == "cancelled"

    def test_append_output(self) -> None:
        job = JobRecord("1", "echo")
        for i in range(60):
            job.append_output(f"line {i}")
        assert len(job.output_tail) == 50  # max tail lines

    def test_elapsed_display(self) -> None:
        job = JobRecord("1", "echo")
        display = job.elapsed_display
        assert isinstance(display, str)
        # Should contain time unit
        assert any(unit in display for unit in ("ms", "s", "m"))

    def test_to_dict(self) -> None:
        job = JobRecord("42", "echo hello", cwd="/home", task_id="task-1")
        d = job.to_dict()
        assert d["job_id"] == "42"
        assert d["command"] == "echo hello"
        assert d["cwd"] == "/home"
        assert d["task_id"] == "task-1"


class TestJobCenter:
    def test_create_job(self) -> None:
        center = JobCenter()
        job = center.create_job("ls -la", cwd="/tmp")
        assert job.job_id == "1"
        assert job.command == "ls -la"
        assert job.status == "running"

    def test_auto_increment_ids(self) -> None:
        center = JobCenter()
        j1 = center.create_job("echo 1")
        j2 = center.create_job("echo 2")
        j3 = center.create_job("echo 3")
        assert j1.job_id == "1"
        assert j2.job_id == "2"
        assert j3.job_id == "3"

    def test_get_job(self) -> None:
        center = JobCenter()
        job = center.create_job("test")
        assert center.get_job("1") is job
        assert center.get_job("999") is None

    def test_list_jobs(self) -> None:
        center = JobCenter()
        center.create_job("a")
        center.create_job("b")
        center.create_job("c")
        all_jobs = center.list_jobs()
        assert len(all_jobs) == 3

    def test_list_jobs_by_status(self) -> None:
        center = JobCenter()
        j1 = center.create_job("running-1")
        j2 = center.create_job("done-1")
        j2.complete(0)
        running = center.list_jobs(status="running")
        completed = center.list_jobs(status="completed")
        assert len(running) == 1
        assert len(completed) == 1

    def test_cancel_job(self) -> None:
        center = JobCenter()
        job = center.create_job("cancellable")
        assert center.cancel_job(job.job_id) is True
        assert job.status == "cancelled"

    def test_cancel_nonexistent(self) -> None:
        center = JobCenter()
        assert center.cancel_job("999") is False

    def test_cancel_completed(self) -> None:
        center = JobCenter()
        job = center.create_job("done")
        job.complete(0)
        assert center.cancel_job(job.job_id) is False

    def test_get_output(self) -> None:
        center = JobCenter()
        job = center.create_job("output-test")
        job.append_output("line 1")
        job.append_output("line 2")
        job.append_output("line 3")
        output = center.get_output(job.job_id, lines=2)
        assert len(output) == 2
        assert output[-1] == "line 3"

    def test_get_output_nonexistent(self) -> None:
        center = JobCenter()
        assert center.get_output("999") == []

    def test_cleanup_completed(self) -> None:
        center = JobCenter()
        for i in range(10):
            job = center.create_job(f"job-{i}")
            job.complete(0)
        removed = center.cleanup_completed(max_keep=5)
        assert removed == 5
        assert len(center.jobs) == 5

    def test_summary(self) -> None:
        center = JobCenter()
        j1 = center.create_job("running")
        j2 = center.create_job("completed")
        j2.complete(0)
        j3 = center.create_job("failed")
        j3.complete(1)
        j4 = center.create_job("cancelled")
        j4.cancel()

        s = center.summary()
        assert s["total"] == 4
        assert s["running"] == 1
        assert s["completed"] == 1
        assert s["failed"] == 1
        assert s["cancelled"] == 1

    def test_cancel_with_shell_manager(self) -> None:
        center = JobCenter()
        sm = ShellManager()
        job = center.create_job("test", shell_session_id="sess-1")
        # No shell exists for sess-1, but cancel should still work
        assert center.cancel_job(job.job_id, shell_manager=sm) is True
        assert job.status == "cancelled"
