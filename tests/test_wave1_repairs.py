"""Focused end-to-end tests for the Wave 1 transport and session repairs."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_terminal_ui.commands import CommandProcessor
from agent_terminal_ui.screens.agent_view import AgentViewScreen
from agent_terminal_ui.widgets.conversation import Conversation


@pytest.mark.asyncio
async def test_two_deltas_append_to_one_response_widget(app) -> None:
    """Normalized deltas should update one response instead of mounting chunks."""
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app._get_main_screen()
        assert screen is not None
        conversation = screen.query_one("#conversation", Conversation)

        await screen.handle_agent_event({"type": "text_delta", "content": "hello "})
        first_response = conversation._current_response
        await screen.handle_agent_event({"type": "text_delta", "content": "world"})

        assert first_response is not None
        assert conversation._current_response is first_response
        assert first_response.content == "hello world"

        await screen.handle_agent_event({"type": "turn_end"})
        await screen.handle_agent_event({"type": "text_delta", "content": "next"})

        assert conversation._current_response is not first_response
        assert conversation._current_response is not None
        assert conversation._current_response.content == "next"


@pytest.mark.asyncio
async def test_start_bg_opens_agent_view(fake_client) -> None:
    """The --bg/start_bg option should enter the now-valid agent screen mode."""
    from agent_terminal_ui.app import AgentApp

    app = AgentApp(client=fake_client, start_bg=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, AgentViewScreen)


@pytest.mark.asyncio
async def test_bg_uses_public_current_session_identity() -> None:
    """Backgrounding should not depend on the removed private _session_id name."""
    app = MagicMock()
    app.current_session_id = "session-background"
    app.query_one.return_value = AsyncMock()
    app.notify = MagicMock()
    app.switch_mode = MagicMock()

    await CommandProcessor(app).cmd_bg("")

    app.notify.assert_called_once()
    assert "session-" in app.notify.call_args.args[0]
    app.switch_mode.assert_called_once_with("agents")


@pytest.mark.asyncio
async def test_export_writes_the_shown_exchange_under_the_session(
    app, tmp_path, monkeypatch
) -> None:
    """Export writes what the person saw, named by the streamed session."""
    from agent_terminal_ui.app import AgentEventReceived

    monkeypatch.chdir(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app._get_main_screen()
        await screen.add_user_message("list the zones")
        for event in (
            {"type": "session_started", "session_id": "session-export"},
            {"type": "text_delta", "content": "arpa, "},
            {"type": "text_delta", "content": "home"},
        ):
            await app.on_agent_event_received(AgentEventReceived(event))
        await app._cmd_processor.cmd_export("wave1")

    text = (tmp_path / "wave1.md").read_text()
    assert "session-export" in text
    assert "### USER\nlist the zones" in text
    assert "### AGENT\narpa, home" in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event",
    [{}, {"type": None}, {"type": 7}, {"type": []}, {"type": {}}, {"type": "unknown"}],
)
async def test_unknown_event_types_preserve_current_response(
    app, event: dict[str, Any]
) -> None:
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app._get_main_screen()
        assert screen is not None
        conversation = screen.query_one("#conversation", Conversation)
        await screen.handle_agent_event({"type": "text_delta", "content": "unchanged"})
        response = conversation._current_response
        await screen.handle_agent_event(event)
        assert conversation._current_response is response
        assert response is not None
        assert response.content == "unchanged"
