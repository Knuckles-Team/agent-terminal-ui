"""Third-pass coverage uplift for terminal UI ``app.py`` internals.

Drives the high-level ``AgentApp`` through ``run_test`` to exercise
``on_input_text_area_submitted``, queue interaction,
``_show_tool_approval_modal``, and
``_handle_tool_approval_result`` branches that are not reachable via the
simpler handlers already covered in ``test_tui_components.py``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def agent_app(monkeypatch):
    """Return a fresh AgentApp instance with a local Arbora endpoint."""
    monkeypatch.setenv("AGENT_URL", "http://localhost:8000")
    monkeypatch.delenv("AGENT_BEARER_TOKEN", raising=False)
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
async def test_app_uses_arbora_endpoint_and_caller_token(monkeypatch):
    """The app uses the same authenticated Arbora client as headless mode."""
    monkeypatch.setenv("AGENT_BEARER_TOKEN", "caller-token")
    monkeypatch.setenv("AGENT_URL", "http://localhost:8000")
    from agent_terminal_ui.app import AgentApp

    app = AgentApp()
    assert app._client.a2a_url == "http://localhost:8000/a2a"
    assert app._client._http_client.headers["Authorization"] == "Bearer caller-token"


@pytest.mark.asyncio
async def test_app_derives_a2a_url_without_caller_token(monkeypatch):
    monkeypatch.delenv("AGENT_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("AGENT_URL", "http://localhost:8000")
    from agent_terminal_ui.app import AgentApp

    app = AgentApp()
    assert app._client.a2a_url == "http://localhost:8000/a2a"
    assert "Authorization" not in app._client._http_client.headers


@pytest.mark.asyncio
async def test_theme_tokens_and_no_color_fallback(monkeypatch):
    """The Python theme contract retains default, fallback and monochrome mode."""
    from agent_terminal_ui.app import AgentApp
    from agent_terminal_ui.client import AgentClient

    monkeypatch.delenv("NO_COLOR", raising=False)
    client = AgentClient(base_url="http://localhost")
    try:
        default = AgentApp(client=client)
        assert default.theme == "tokyo-night"
        assert default.no_color is False
        fallback = AgentApp(theme_name="missing-theme", client=client)
        assert fallback.theme == "tokyo-night"
        for value in ("1", ""):
            monkeypatch.setenv("NO_COLOR", value)
            monochrome = AgentApp(theme_name="nord", client=client)
            assert monochrome.no_color is True
            assert monochrome.theme == "nord"
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("theme_name", ["tokyo-night", "nord", "gruvbox", "textual-light", "canopy"])
async def test_baseline_theme_tokens_meet_text_contrast(theme_name):
    from textual.color import Color

    from agent_terminal_ui.app import AgentApp
    from agent_terminal_ui.client import AgentClient

    def luminance(value):
        color = Color.parse(value)
        channels = [channel / 255 for channel in (color.r, color.g, color.b)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
        return sum(v * weight for v, weight in zip(linear, [0.2126, 0.7152, 0.0722]))

    client = AgentClient(base_url="http://localhost")
    try:
        app = AgentApp(theme_name=theme_name, client=client)
        assert app.theme == theme_name
        tokens = app.current_theme.to_color_system().generate()
        for token in ("primary", "secondary", "accent", "warning", "error", "success",
                      "foreground", "background", "surface", "panel"):
            assert Color.parse(tokens[token])
        light, dark = sorted([luminance(tokens["foreground"]), luminance(tokens["background"])], reverse=True)
        assert (light + 0.05) / (dark + 0.05) >= 4.5
    finally:
        await client.aclose()


# spec: TUI-RUNTIME-R008.2.3.1
@pytest.mark.asyncio
async def test_selection_clear_before_mount_and_on_active_screen(fake_client):
    """Input mounting may clear selection before the first screen is active."""
    from textual.selection import Selection
    from textual.widgets import Static

    from agent_terminal_ui.app import AgentApp

    app = AgentApp(client=fake_client)
    app.clear_selection()
    async with app.run_test() as pilot:
        label = Static("Selected text", id="selection-regression")
        await app.screen.mount(label)
        await pilot.pause()
        app.screen.selections = {label: Selection(None, None)}
        assert app.screen.get_selected_text() == "Selected text"
        app.clear_selection()
        assert app.screen.get_selected_text() is None
