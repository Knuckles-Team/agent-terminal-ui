"""Mounted main-view presentation across small and restored viewports."""

from unittest.mock import AsyncMock

import pytest

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.tui.input_text_area import InputTextArea
from agent_terminal_ui.widgets.conversation import Conversation

pytestmark = pytest.mark.spec("TUI-RUNTIME-R008")


@pytest.mark.asyncio
async def test_multiline_composer_keeps_reading_view_available_after_resize(fake_client: AsyncMock) -> None:
    app = AgentApp(client=fake_client)
    async with app.run_test(size=(120, 40)) as pilot:
        composer = app.screen.query_one(InputTextArea)
        conversation = app.screen.query_one(Conversation)
        await conversation.add_user_message("Readable reply\n" * 60)
        composer.load_text("Unfinished prompt\n" * 8)
        composer.focus()
        for width, height in [(120, 40), (40, 12), (60, 20), (120, 40)]:
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            assert app.screen.region.contains_region(composer.region)
            assert conversation.content_region.height >= 1
            assert conversation.content_region.width >= 1
            assert app.focused is composer
            assert composer.text == "Unfinished prompt\n" * 8


@pytest.mark.asyncio
async def test_sidebar_shortcut_moves_focus_into_its_keyboard_controls(fake_client: AsyncMock) -> None:
    app = AgentApp(client=fake_client)
    async with app.run_test(size=(100, 30)) as pilot:
        composer = app.screen.query_one(InputTextArea)
        composer.load_text("Keep this draft")
        sidebar = app.screen.query_one("#sidebar")
        await pilot.press("ctrl+b")
        assert not sidebar.display
        await pilot.press("ctrl+b")
        assert sidebar.display
        assert app.focused is not None and sidebar in app.focused.ancestors
        await pilot.press("right")
        await pilot.pause()
        assert app.screen.query_one("#sidebar-tabs").active == "graph-tab"
        await pilot.resize_terminal(40, 12)
        await pilot.pause()
        assert sidebar in app.focused.ancestors
        await pilot.press("ctrl+b")
        assert not sidebar.display
        assert app.focused is composer
        assert composer.text == "Keep this draft"
