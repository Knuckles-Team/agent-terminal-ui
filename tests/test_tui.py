import pytest

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.tui.input_text_area import InputTextArea
from agent_terminal_ui.tui.status_line import StatusLine


@pytest.mark.asyncio
async def test_app_modes():
    app = AgentApp()
    async with app.run_test() as pilot:
        # Check initial state
        assert app._agent_mode == "ask"
        app.query_one(StatusLine)

        # Test mode change via /plan
        app.query_one(InputTextArea)
        await pilot.click(InputTextArea)
        await pilot.press("/", "p", "l", "a", "n", "enter")
        await pilot.pause()

        assert app._agent_mode == "plan"

        # Test mode change via /build
        await pilot.press("/", "b", "u", "i", "l", "d", "enter")
        await pilot.pause()

        assert app._agent_mode == "code"

        assert app._agent_mode == "code"
