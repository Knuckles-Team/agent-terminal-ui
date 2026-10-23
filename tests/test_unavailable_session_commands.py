"""Mounted refusal evidence; no served session or model-policy acceptance."""

from unittest.mock import AsyncMock, Mock

import pytest

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.tui.input_text_area import InputTextArea

pytestmark = pytest.mark.spec("TUI-RUNTIME-R012.4.3.3")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    ["/bg", "/bg now", "/attach", "/attach session-other", "/fast", "/fast on", "/fast off", "alt+o"],
)
async def test_unsupported_actions_refuse_without_state_changes(
    command: str, fake_client: AsyncMock,
) -> None:
    fake_client.stream = Mock(side_effect=AssertionError("must not start a turn"))
    app = AgentApp(client=fake_client)
    app.remember_session_id("session-current")
    app._user_message_queue = [{"message": "preserve queued input"}]
    manager = Mock()
    manager._get_conn.side_effect = AssertionError("must not access session storage")
    app._session_manager = manager
    async with app.run_test(size=(120, 35)) as pilot:
        composer = app.screen.query_one(InputTextArea)
        screen = app.screen
        app.notify = Mock()
        fake_client.reset_mock()
        if command == "alt+o":
            await pilot.press("alt+o")
        else:
            composer.load_text(command)
            await pilot.press("enter")
        await pilot.pause()
        app.notify.assert_called_once()
        assert "unavailable" in app.notify.call_args.args[0].lower()
        assert app.notify.call_args.kwargs["severity"] == "warning"
        assert app.current_session_id == "session-current"
        assert app._user_message_queue == [{"message": "preserve queued input"}]
        assert not getattr(app, "_fast_mode", False)
        assert app.screen is screen
        assert app.focused is composer
        assert composer.text == ""
        assert manager.mock_calls == []
        fake_client.stream.assert_not_called()
        assert fake_client.mock_calls == []
