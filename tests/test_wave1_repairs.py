"""Focused end-to-end tests for the Wave 1 transport and session repairs."""

from __future__ import annotations

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
async def test_propagated_session_identity_drives_export(
    app, tmp_path, monkeypatch
) -> None:
    """An identity received from the stream should be the exported chat id."""
    from agent_terminal_ui.app import AgentEventReceived

    monkeypatch.chdir(tmp_path)
    app._client.get_chat = AsyncMock(
        return_value={"messages": [{"role": "assistant", "content": "done"}]}
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        await app.on_agent_event_received(
            AgentEventReceived(
                {"type": "session_started", "session_id": "session-export"}
            )
        )
        await app._cmd_processor.cmd_export("wave1")

    app._client.get_chat.assert_awaited_once_with("session-export")
    assert (tmp_path / "wave1.md").exists()
