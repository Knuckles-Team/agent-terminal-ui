"""Third-pass coverage uplift for terminal UI ``app.py`` internals.

Drives the high-level ``AgentApp`` through ``run_test`` to exercise
``on_input_text_area_submitted``, queue interaction,
``_resume_session``, ``_show_tool_approval_modal``, and
``_handle_tool_approval_result`` branches that are not reachable via the
simpler handlers already covered in ``test_tui_components.py``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def agent_app(monkeypatch):
    """Ensure ACP_URL is unset and return a fresh AgentApp instance."""
    monkeypatch.delenv("ACP_URL", raising=False)
    from agent_terminal_ui.app import AgentApp

    return AgentApp()


@pytest.mark.asyncio
async def test_submitted_routes_command_to_processor(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        # Replace cmd_processor.process with AsyncMock returning True
        agent_app._cmd_processor.process = AsyncMock(return_value=True)
        event = SimpleNamespace(value="/help")
        await agent_app.on_input_text_area_submitted(event)
        agent_app._cmd_processor.process.assert_awaited_once()


@pytest.mark.asyncio
async def test_submitted_empty_is_ignored(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        event = SimpleNamespace(value="   ")
        await agent_app.on_input_text_area_submitted(event)


@pytest.mark.asyncio
async def test_submitted_bang_prefix_executes_bash(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        agent_app._cmd_processor.process = AsyncMock(return_value=False)
        agent_app._submit_prompt = AsyncMock()
        event = SimpleNamespace(value="!echo hi")
        await agent_app.on_input_text_area_submitted(event)
        agent_app._submit_prompt.assert_awaited_once()
        assert "echo hi" in agent_app._submit_prompt.call_args.args[0]


@pytest.mark.asyncio
async def test_submitted_queues_when_processing(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        agent_app._cmd_processor.process = AsyncMock(return_value=False)
        agent_app._is_processing = True
        event = SimpleNamespace(value="additional request")
        await agent_app.on_input_text_area_submitted(event)
        assert len(agent_app._user_message_queue) == 1


@pytest.mark.asyncio
async def test_submitted_combines_related_queued_message(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        agent_app._cmd_processor.process = AsyncMock(return_value=False)
        agent_app._is_processing = True
        agent_app._user_message_queue = [
            {"message": "fix bug A", "parts": [], "timestamp": 0.0}
        ]
        event = SimpleNamespace(value="fix bug B")
        await agent_app.on_input_text_area_submitted(event)
        # The queue entry was replaced with a combined message
        assert agent_app._user_message_queue[-1]["message"] != "fix bug A"


@pytest.mark.asyncio
async def test_submitted_normal_processing(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        agent_app._cmd_processor.process = AsyncMock(return_value=False)
        # Prevent the real @work worker from launching real HTTP calls
        agent_app._run_agent_turn = MagicMock()
        event = SimpleNamespace(value="hello")
        await agent_app.on_input_text_area_submitted(event)
        agent_app._run_agent_turn.assert_called_once()
        assert agent_app._is_processing is True


@pytest.mark.asyncio
async def test_resume_session_text_and_list_content(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        # Mock the client's get_chat
        agent_app._client.get_chat = AsyncMock(
            return_value={
                "messages": [
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "hello!"},
                    {
                        "role": "assistant",
                        "content": ["nested string", {"text": "item text"}],
                    },
                ]
            }
        )
        # Call the worker coroutine directly (bypassing @work decorator)
        coro = agent_app._resume_session.__wrapped__(agent_app, "session-1")
        await coro
        assert agent_app._current_session_id == "session-1"


@pytest.mark.asyncio
async def test_resume_session_no_chat_id(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        coro = agent_app._resume_session.__wrapped__(agent_app, None)
        await coro  # returns early without error


@pytest.mark.asyncio
async def test_show_tool_approval_modal_no_pending(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        # When no pending approvals, no screen is pushed
        agent_app._pending_tool_calls = {}
        agent_app.push_screen = MagicMock()
        agent_app._show_tool_approval_modal()
        agent_app.push_screen.assert_not_called()


@pytest.mark.asyncio
async def test_show_tool_approval_modal_with_pending(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        agent_app._pending_tool_calls = {
            "c1": {
                "call_id": "c1",
                "name": "read",
                "arguments": "{}",
                "needs_approval": True,
            }
        }
        agent_app.push_screen = MagicMock()
        agent_app._show_tool_approval_modal()
        agent_app.push_screen.assert_called_once()


@pytest.mark.asyncio
async def test_handle_tool_approval_result_none_returns_early(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        agent_app._handle_tool_approval_result(None)
        # No exceptions; no state change
        assert agent_app._is_processing is False


@pytest.mark.asyncio
async def test_handle_tool_approval_result_with_decisions(agent_app):
    from agent_terminal_ui.tui.tool_approval_screen import ToolApprovalResult

    async with agent_app.run_test() as pilot:
        await pilot.pause()
        agent_app._pending_tool_calls = {
            "c1": {
                "call_id": "c1",
                "name": "read",
                "arguments": "{}",
                "needs_approval": True,
            }
        }
        agent_app._run_agent_turn_with_permissions = MagicMock()
        result = ToolApprovalResult(decisions={"c1": "accept"}, feedback=None)
        agent_app._handle_tool_approval_result(result)
        await pilot.pause()
        assert agent_app._is_processing is True
        agent_app._run_agent_turn_with_permissions.assert_called_once()


@pytest.mark.asyncio
async def test_acp_url_env_var_overrides_derived_url(monkeypatch):
    """D-FE-2(b): ``ACP_URL`` is now actually read, not silently dropped."""
    monkeypatch.setenv("ACP_URL", "http://otherhost:9999/acp")
    monkeypatch.setenv("AGENT_URL", "http://localhost:8000")
    from agent_terminal_ui.app import AgentApp

    app = AgentApp()
    assert app._client.acp_url == "http://otherhost:9999/acp"


@pytest.mark.asyncio
async def test_acp_url_defaults_to_agent_url_derivation(monkeypatch):
    monkeypatch.delenv("ACP_URL", raising=False)
    monkeypatch.setenv("AGENT_URL", "http://localhost:8000")
    from agent_terminal_ui.app import AgentApp

    app = AgentApp()
    assert app._client.acp_url == "http://localhost:8000/acp"


