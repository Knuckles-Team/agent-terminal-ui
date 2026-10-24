"""Full-application keyboard history admission, not live producer acceptance."""

import asyncio
import json

import httpx
import pytest
from textual.widgets import DataTable, Static

from agent_terminal_ui.tui.history_screen import HistoryScreen
from agent_terminal_ui.tui.input_text_area import InputTextArea
from tests.test_mounted_command_matrix import mounted
from tests.test_task_history import response, task

pytestmark = [pytest.mark.asyncio, pytest.mark.spec("TUI-RUNTIME-R012.3.1")]


async def test_initial_history_read_can_close_and_reopen_without_late_content() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    cancelled = asyncio.Event()
    calls: list[str] = []

    async def serve(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/a2a":
            return httpx.Response(404)
        body = json.loads(request.content)
        calls.append(body["method"])
        assert body["method"] == "tasks/list"
        assert body["params"] == {"limit": 50}
        if len(calls) == 1:
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.set()
                await release.wait()
            return response({"tasks": [task(1)], "nextCursor": None})
        return response({"tasks": [task(2)], "nextCursor": None})

    async with mounted(serve) as (app, pilot):
        composer = app.screen.query_one(InputTextArea)
        composer.load_text("/history")
        pressing = asyncio.create_task(pilot.press("enter"))
        try:
            await asyncio.wait_for(started.wait(), 2)
            await asyncio.sleep(0)
            assert isinstance(app.screen, HistoryScreen)
            old_screen = app.screen
            await asyncio.wait_for(pressing, 2)
            assert old_screen.query_one(DataTable).row_count == 0
            assert "Refreshing" in str(old_screen.query_one("#history-reply", Static).content)
            await pilot.press("r", "n", "p", "enter")
            assert calls == ["tasks/list"]
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, HistoryScreen)
            assert app.focused is composer
            await asyncio.wait_for(cancelled.wait(), 2)
            composer.load_text("/history")
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, HistoryScreen)
            assert app.screen is not old_screen
            table = app.screen.query_one(DataTable)
            assert str(table.get_cell_at((0, 1))) == "work-item:2"
            release.set()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert str(table.get_cell_at((0, 1))) == "work-item:2"
            assert old_screen.page["tasks"] == []
            assert calls == ["tasks/list", "tasks/list"]
            assert app.agent_client.current_session_id is None
            assert app.agent_client.current_task_id is None
        finally:
            release.set()
            await pressing


@pytest.mark.parametrize("outcome", ["denied", "malformed"])
async def test_initial_history_failure_is_retryable_without_a_model_turn(outcome: str) -> None:
    calls: list[str] = []

    def serve(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/a2a":
            return httpx.Response(404)
        body = json.loads(request.content)
        calls.append(body["method"])
        assert body["method"] == "tasks/list"
        if len(calls) == 1:
            return httpx.Response(403) if outcome == "denied" else response({})
        return response({"tasks": [task(2)], "nextCursor": None})

    async with mounted(serve) as (app, pilot):
        composer = app.screen.query_one(InputTextArea)
        composer.load_text("/history")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, HistoryScreen)
        screen = app.screen
        assert screen.query_one(DataTable).row_count == 0
        assert str(screen.query_one("#history-reply", Static).content) == "Task history unavailable."
        await pilot.press("r")
        await pilot.pause()
        assert str(screen.query_one(DataTable).get_cell_at((0, 1))) == "work-item:2"
        await pilot.press("escape")
        await pilot.pause()
        assert app.focused is composer
        assert calls == ["tasks/list", "tasks/list"]
        assert not app._is_processing
