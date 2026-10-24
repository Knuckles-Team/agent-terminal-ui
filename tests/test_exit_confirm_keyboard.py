"""Keyboard access to the production exit-confirmation controls."""

from unittest.mock import AsyncMock

import pytest
from textual.app import App

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.tui.exit_confirm_screen import ExitConfirmScreen
from agent_terminal_ui.tui.input_text_area import InputTextArea

pytestmark = pytest.mark.spec("TUI-RUNTIME-R008")


@pytest.mark.asyncio
@pytest.mark.parametrize("direction", ["left", "right", "up", "down"])
async def test_arrow_navigation_and_space_activate_once(direction: str) -> None:
    results: list[bool] = []

    class Host(App):
        def on_mount(self) -> None:
            self.push_screen(ExitConfirmScreen(callback=results.append))

    app = Host()
    async with app.run_test() as pilot:
        assert app.focused is app.screen.query_one("#no")
        await pilot.press(direction)
        assert app.focused is app.screen.query_one("#yes")
        await pilot.press(direction)
        assert app.focused is app.screen.query_one("#no")
        await pilot.press(direction, "space")
        await pilot.pause()
        assert results == [True]
        assert not isinstance(app.screen, ExitConfirmScreen)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_key", ["space", "enter", "n"])
async def test_cancel_restores_composer_focus_and_text(
    fake_client: AsyncMock, cancel_key: str
) -> None:
    app = AgentApp(client=fake_client)
    async with app.run_test() as pilot:
        composer = app.screen.query_one(InputTextArea)
        composer.load_text("Unfinished prompt")
        await pilot.press("ctrl+d")
        assert isinstance(app.screen, ExitConfirmScreen)
        assert app.focused is app.screen.query_one("#no")
        await pilot.press(cancel_key)
        await pilot.pause()
        assert not isinstance(app.screen, ExitConfirmScreen)
        assert app.focused is composer
        assert composer.text == "Unfinished prompt"
