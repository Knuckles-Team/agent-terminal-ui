"""Regression coverage for the documented theme keyboard route."""

from unittest.mock import AsyncMock

import pytest

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.tui.input_text_area import InputTextArea

pytestmark = pytest.mark.spec("TUI-RUNTIME-R015.53")


@pytest.mark.asyncio
@pytest.mark.parametrize("no_color", [False, True])
async def test_theme_shortcut_cycles_without_changing_composer(
    fake_client: AsyncMock, monkeypatch: pytest.MonkeyPatch, no_color: bool
) -> None:
    if no_color:
        monkeypatch.setenv("NO_COLOR", "1")
    else:
        monkeypatch.delenv("NO_COLOR", raising=False)
    app = AgentApp(client=fake_client)
    async with app.run_test(size=(100, 30)) as pilot:
        composer = app.screen.query_one(InputTextArea)
        composer.load_text("Keep this unfinished prompt")
        initial = app.theme
        themes = list(app.available_themes)
        start = themes.index(initial)
        for offset in range(1, len(themes) + 1):
            await pilot.press("alt+shift+t")
            await pilot.pause()
            assert app.theme == themes[(start + offset) % len(themes)]
            assert app.focused is composer
            assert composer.text == "Keep this unfinished prompt"
            assert app.no_color is no_color
        assert app.theme == initial
