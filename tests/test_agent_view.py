"""Tests for Agent View and Background Runner (TUI-20, TUI-21)."""

from __future__ import annotations

import time

import pytest

from agent_terminal_ui.background_runner import BackgroundAgentRunner, BackgroundSession
from agent_terminal_ui.screens.agent_view import AgentSessionRow


class TestAgentSessionRow:
    """Test AgentSessionRow display logic."""

    def test_status_icons(self):
        assert AgentSessionRow("s1", status="working").status_icon == "🟢"
        assert AgentSessionRow("s1", status="waiting").status_icon == "🟡"
        assert AgentSessionRow("s1", status="done").status_icon == "✅"
        assert AgentSessionRow("s1", status="failed").status_icon == "❌"
        assert AgentSessionRow("s1", status="cancelled").status_icon == "🚫"
        assert AgentSessionRow("s1", status="unknown").status_icon == "❓"

    def test_elapsed_display_seconds(self):
        row = AgentSessionRow("s1", last_activity=time.time() - 30)
        assert "s ago" in row.elapsed_display

    def test_elapsed_display_minutes(self):
        row = AgentSessionRow("s1", last_activity=time.time() - 300)
        assert "m ago" in row.elapsed_display

    def test_elapsed_display_hours(self):
        row = AgentSessionRow("s1", last_activity=time.time() - 7200)
        assert "h ago" in row.elapsed_display

    def test_preview_truncation(self):
        row = AgentSessionRow("s1", last_response="x" * 100)
        assert len(row.preview) <= 63  # 60 + "..."
        assert row.preview.endswith("...")

    def test_preview_short(self):
        row = AgentSessionRow("s1", last_response="hello")
        assert row.preview == "hello"

    def test_preview_empty(self):
        row = AgentSessionRow("s1", last_response="")
        assert row.preview == "(no output yet)"

    def test_preview_newlines(self):
        row = AgentSessionRow("s1", last_response="line1\nline2\nline3")
        assert "\n" not in row.preview

    def test_title_default(self):
        row = AgentSessionRow("abcdefghijk")
        assert row.title == "abcdefgh"  # First 8 chars of session_id

    def test_title_custom(self):
        row = AgentSessionRow("s1", title="My Session")
        assert row.title == "My Session"

    def test_goal_id(self):
        row = AgentSessionRow("s1", goal_id="goal-123")
        assert row.goal_id == "goal-123"


class TestBackgroundAgentRunner:
    """Test BackgroundAgentRunner session management."""

    def test_create_session(self):
        runner = BackgroundAgentRunner()
        session = runner.create_session(title="Test")
        assert session.title == "Test"
        assert session.status == "running"
        assert session.id in runner.sessions

    def test_create_with_goal(self):
        runner = BackgroundAgentRunner()
        session = runner.create_session(title="Goal", goal_id="g1")
        assert session.goal_id == "g1"

    def test_max_concurrent(self):
        runner = BackgroundAgentRunner(max_concurrent=2)
        runner.create_session(title="S1")
        runner.create_session(title="S2")
        with pytest.raises(RuntimeError, match="Max concurrent"):
            runner.create_session(title="S3")

    def test_update_session(self):
        runner = BackgroundAgentRunner()
        session = runner.create_session()
        runner.update_session(
            session.id,
            status="waiting",
            last_response="What should I do?",
            needs_input=True,
            iteration=3,
        )
        updated = runner.get_session(session.id)
        assert updated is not None
        assert updated.status == "waiting"
        assert updated.last_response == "What should I do?"
        assert updated.needs_input is True
        assert updated.iteration == 3

    def test_update_nonexistent(self):
        runner = BackgroundAgentRunner()
        runner.update_session("fake-id", status="done")  # Should not raise

    def test_cancel_session(self):
        runner = BackgroundAgentRunner()
        session = runner.create_session()
        assert runner.cancel_session(session.id) is True
        cancelled_session = runner.get_session(session.id)
        assert cancelled_session is not None
        assert cancelled_session.status == "cancelled"

    def test_cancel_nonexistent(self):
        runner = BackgroundAgentRunner()
        assert runner.cancel_session("fake") is False

    def test_cancel_already_done(self):
        runner = BackgroundAgentRunner()
        session = runner.create_session()
        runner.update_session(session.id, status="done")
        assert runner.cancel_session(session.id) is False

    def test_remove_session(self):
        runner = BackgroundAgentRunner()
        session = runner.create_session()
        assert runner.remove_session(session.id) is True
        assert runner.get_session(session.id) is None

    def test_remove_running_cancels_first(self):
        runner = BackgroundAgentRunner()
        session = runner.create_session()
        assert runner.remove_session(session.id) is True

    def test_list_sessions_all(self):
        runner = BackgroundAgentRunner()
        runner.create_session(title="S1")
        runner.create_session(title="S2")
        assert len(runner.list_sessions()) == 2

    def test_list_sessions_by_status(self):
        runner = BackgroundAgentRunner()
        s1 = runner.create_session(title="S1")
        runner.create_session(title="S2")
        runner.update_session(s1.id, status="done")
        assert len(runner.list_sessions(status="running")) == 1
        assert len(runner.list_sessions(status="done")) == 1

    def test_get_summary(self):
        runner = BackgroundAgentRunner()
        s1 = runner.create_session()
        runner.create_session()
        runner.update_session(s1.id, status="done")
        summary = runner.get_summary()
        assert summary["total"] == 2
        assert summary.get("done", 0) == 1
        assert summary.get("running", 0) == 1

    def test_recover_interrupted(self):
        runner = BackgroundAgentRunner()
        s1 = runner.create_session()
        s2 = runner.create_session()
        runner.update_session(s2.id, status="done")
        interrupted = runner.recover_interrupted()
        assert len(interrupted) == 1
        assert interrupted[0].id == s1.id
        assert interrupted[0].status == "failed"
        assert "restart" in interrupted[0].error.lower()


class TestBackgroundSession:
    """Test BackgroundSession dataclass."""

    def test_defaults(self):
        session = BackgroundSession()
        assert session.status == "running"
        assert session.needs_input is False
        assert session.goal_id == ""
        assert session.iteration == 0
        assert session.max_iterations == 20
        assert session.error == ""
        assert session.task is None
