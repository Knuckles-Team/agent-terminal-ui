"""Mounted settings and tool-table resize journeys."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Checkbox, DataTable, Input

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.screens.settings import SettingsScreen
from agent_terminal_ui.settings import AppSettings
from agent_terminal_ui.tui.mcp_screen import MCPScreen
from agent_terminal_ui.tui.input_text_area import InputTextArea

pytestmark = pytest.mark.spec("TUI-RUNTIME-R008")
SIZES = [(120, 40), (40, 12), (60, 20), (120, 40)]


@pytest.mark.asyncio
async def test_settings_search_and_control_survive_resize(
    fake_client: AsyncMock, tmp_path: Path,
) -> None:
    settings = AppSettings(tmp_path / "settings.toml")
    app = AgentApp(client=fake_client)
    async with app.run_test(size=SIZES[0]) as pilot:
        composer = app.screen.query_one(InputTextArea)
        composer.load_text("Unfinished settings prompt")
        await app.push_screen(SettingsScreen(settings))
        screen = app.screen
        search = screen.query_one("#settings-search", Input)
        search.focus()
        await pilot.press(*"sidebar")
        checkbox = next(item for item in screen.query(Checkbox) if item.name == "sidebar_visible")
        original = checkbox.value
        for width, height in SIZES:
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            dialog = screen.query_one("#settings-container")
            assert screen.region.contains_region(dialog.region)
            assert dialog.content_region.contains_region(search.region)
            assert search.value == "sidebar"
            assert app.focused is search
            await pilot.press("tab", "tab")
            assert app.focused is checkbox
            area = screen.query_one("#settings-list", VerticalScroll)
            assert area.content_region.height >= 3
            assert area.content_region.contains_region(checkbox.region)
            search.focus()
        await pilot.press("tab", "tab", "space")
        assert settings.get("sidebar_visible") is not original
        assert AppSettings(tmp_path / "settings.toml").get("sidebar_visible") is not original
        await pilot.press("escape")
        assert app.screen is not screen
        assert app.focused is composer
        assert composer.text == "Unfinished settings prompt"
        await app.push_screen(SettingsScreen(AppSettings(tmp_path / "settings.toml")))
        restored = next(item for item in app.screen.query(Checkbox) if item.name == "sidebar_visible")
        assert restored.value is not original
        await pilot.press("escape")
        assert app.focused is composer


@pytest.mark.asyncio
async def test_mcp_table_keeps_selected_row_visible_after_resize(fake_client: AsyncMock) -> None:
    app = AgentApp(client=fake_client)
    tools = [{"id": f"tool-{i}", "name": f"Tool {i}", "description": "Description"} for i in range(30)]
    async with app.run_test(size=SIZES[0]) as pilot:
        fake_client.list_mcp_tools.return_value = tools
        composer = app.screen.query_one(InputTextArea)
        composer.load_text("/mcp")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, MCPScreen)
        screen = app.screen
        table = screen.query_one(DataTable)
        table.focus()
        await pilot.press(*(["down"] * 29))
        assert table.cursor_row == 29
        for width, height in SIZES:
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            dialog = screen.query_one("#mcp-dialog")
            assert screen.region.contains_region(dialog.region)
            assert dialog.content_region.contains_region(table.region)
            assert table.content_region.height >= 2
            assert table.cursor_row == 29
            assert app.focused is table
            assert table.scroll_y <= table.cursor_row < table.scroll_y + table.content_region.height - 1
        await pilot.press("up")
        assert table.cursor_row == 28
        await pilot.press("escape")
        assert app.screen is not screen
        assert app.focused is composer
        assert composer.text == ""
        fake_client.list_mcp_tools.return_value = []
        composer.load_text("/mcp")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, MCPScreen)
        assert app.screen.query_one(DataTable).row_count == 0
        await pilot.resize_terminal(40, 12)
        await pilot.press("escape")
        assert app.focused is composer
        assert not isinstance(app.screen, MCPScreen)


@pytest.mark.asyncio
async def test_settings_active_field_remains_visible_during_resize(
    fake_client: AsyncMock, tmp_path: Path,
) -> None:
    app = AgentApp(client=fake_client)
    async with app.run_test(size=SIZES[0]) as pilot:
        await app.push_screen(SettingsScreen(AppSettings(tmp_path / "settings.toml")))
        screen = app.screen
        field = next(item for item in screen.query(Input) if item.name == "max_log_lines")
        field.focus()
        await pilot.pause()
        for width, height in SIZES:
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            area = screen.query_one("#settings-list", VerticalScroll)
            assert app.focused is field
            assert area.content_region.contains_region(field.region)
        await pilot.press("escape")
        assert app.screen is not screen
