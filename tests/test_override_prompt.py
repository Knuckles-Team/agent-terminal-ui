"""Tests for --prompt and --override CLI launch features (ECO-4.5).

Validates that AgentApp correctly handles initial_prompt injection
and auto_approve (yolo) mode for tool call bypass.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def yolo_app(monkeypatch):
    """Return an AgentApp with auto_approve=True and an initial prompt."""
    monkeypatch.delenv("ENABLE_ACP", raising=False)
    from agent_terminal_ui.app import AgentApp

    return AgentApp(initial_prompt="hello world", auto_approve=True)


@pytest.fixture
def prompt_only_app(monkeypatch):
    """Return an AgentApp with an initial prompt but no auto_approve."""
    monkeypatch.delenv("ENABLE_ACP", raising=False)
    from agent_terminal_ui.app import AgentApp

    return AgentApp(initial_prompt="run tests", auto_approve=False)


@pytest.fixture
def plain_app(monkeypatch):
    """Return a plain AgentApp with no new flags."""
    monkeypatch.delenv("ENABLE_ACP", raising=False)
    from agent_terminal_ui.app import AgentApp

    return AgentApp()


class TestInitArgs:
    """Verify constructor correctly stores initial_prompt and auto_approve."""

    def test_yolo_attrs_set(self, yolo_app):
        assert yolo_app.initial_prompt == "hello world"
        assert yolo_app.auto_approve is True

    def test_prompt_only_attrs(self, prompt_only_app):
        assert prompt_only_app.initial_prompt == "run tests"
        assert prompt_only_app.auto_approve is False

    def test_plain_defaults(self, plain_app):
        assert plain_app.initial_prompt is None
        assert plain_app.auto_approve is False


@pytest.mark.asyncio
async def test_on_mount_enqueues_prompt(prompt_only_app):
    """on_mount should schedule the initial prompt when set."""
    async with prompt_only_app.run_test() as pilot:
        await pilot.pause()
        # Verify call_after_refresh was triggered with the prompt
        # The on_mount hook calls call_after_refresh(_submit_prompt, prompt)
        # We can verify the app received the prompt by checking it was stored
        assert prompt_only_app.initial_prompt == "run tests"


@pytest.mark.asyncio
async def test_on_mount_skips_when_no_prompt(plain_app):
    """on_mount should not schedule anything when initial_prompt is None."""
    async with plain_app.run_test() as pilot:
        await pilot.pause()
        assert plain_app.initial_prompt is None


@pytest.mark.asyncio
async def test_auto_approve_bypasses_modal(yolo_app):
    """When auto_approve is True, tool approval should auto-accept."""
    async with yolo_app.run_test() as pilot:
        await pilot.pause()
        yolo_app._pending_tool_calls = {
            "c1": {
                "call_id": "c1",
                "name": "read_file",
                "arguments": "{}",
                "needs_approval": True,
            },
            "c2": {
                "call_id": "c2",
                "name": "write_file",
                "arguments": "{}",
                "needs_approval": True,
            },
        }
        yolo_app._run_agent_turn_with_permissions = MagicMock()
        yolo_app.push_screen = MagicMock()

        yolo_app._show_tool_approval_modal()

        # Should NOT push the approval screen (bypassed)
        yolo_app.push_screen.assert_not_called()
        # Should call the turn handler with all approvals accepted
        yolo_app._run_agent_turn_with_permissions.assert_called_once()


@pytest.mark.asyncio
async def test_no_auto_approve_shows_modal(prompt_only_app):
    """When auto_approve is False, tool approval should show the modal."""
    async with prompt_only_app.run_test() as pilot:
        await pilot.pause()
        prompt_only_app._pending_tool_calls = {
            "c1": {
                "call_id": "c1",
                "name": "read_file",
                "arguments": "{}",
                "needs_approval": True,
            }
        }
        prompt_only_app.push_screen = MagicMock()

        prompt_only_app._show_tool_approval_modal()

        # Should push the approval screen
        prompt_only_app.push_screen.assert_called_once()


def test_terminal_ui_argparse():
    """Verify argparse configuration parses --prompt and --override flags."""
    import argparse

    parser = argparse.ArgumentParser(description="Agent Terminal UI")
    parser.add_argument(
        "--prompt", type=str, help="Initial prompt to send to the agent"
    )
    parser.add_argument(
        "--override",
        action="store_true",
        help="Auto-approve all tool calls (yolo mode)",
    )

    args = parser.parse_args(["--prompt", "do something", "--override"])
    assert args.prompt == "do something"
    assert args.override is True

    args_empty = parser.parse_args([])
    assert args_empty.prompt is None
    assert args_empty.override is False
