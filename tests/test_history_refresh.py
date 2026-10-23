"""Mounted first-page refresh; no conversation resume or live producer proof."""

import asyncio
import json

import httpx
import pytest
from textual.app import App
from textual.widgets import DataTable, Static

from agent_terminal_ui.client import AgentClient
from agent_terminal_ui.commands import CommandProcessor
from agent_terminal_ui.tui.history_screen import HistoryScreen
from tests.test_task_history import client_for, response, task

pytestmark = [pytest.mark.asyncio, pytest.mark.spec("TUI-RUNTIME-R012.3.1")]


class HistoryHost(App):
    def __init__(self, client: AgentClient) -> None:
        super().__init__()
        self._client = client

    async def on_mount(self) -> None:
        await CommandProcessor(self).process("/history")


async def test_refresh_restarts_pagination_and_renders_fresh_task_state() -> None:
    calls = []
    first_reads = 0

    def serve(request: httpx.Request) -> httpx.Response:
        nonlocal first_reads
        body = json.loads(request.content)
        calls.append(body)
        if body["method"] == "tasks/get":
            return response(task(2, "old reply"))
        assert body["method"] == "tasks/list"
        if "cursor" in body["params"]:
            assert body["params"] == {"limit": 50, "cursor": "opaque"}
            return response({"tasks": [task(2)], "nextCursor": None})
        assert body["params"] == {"limit": 50}
        first_reads += 1
        current = task(1)
        current["status"]["state"] = "working" if first_reads == 1 else "completed"
        return response({"tasks": [current], "nextCursor": "opaque"})

    client = await client_for(serve)
    client._current_session_id = "active-context"
    try:
        app = HistoryHost(client)
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, HistoryScreen)
            await pilot.press("n", "enter")
            await pilot.pause()
            reply = screen.query_one("#history-reply", Static)
            assert "old reply" in str(reply.content)
            await pilot.press("r")
            await pilot.pause()
            assert first_reads == 2
            table = screen.query_one(DataTable)
            assert str(table.get_cell_at((0, 3))) == "completed"
            assert "old reply" not in str(reply.content)
            assert "Select a task" in str(reply.content)
            assert app.focused is table
            await pilot.press("n")
            await pilot.pause()
            assert str(table.get_cell_at((0, 1))) == "work-item:2"
            assert client.current_session_id == "active-context"
            assert client.current_task_id is None
        assert [call["method"] for call in calls] == [
            "tasks/list", "tasks/list", "tasks/get", "tasks/list", "tasks/list"
        ]
    finally:
        await client.close()


@pytest.mark.parametrize("outcome", ["denied", "malformed", "empty"])
async def test_refresh_clears_old_content_and_can_retry(outcome: str) -> None:
    reads = 0

    def serve(request: httpx.Request) -> httpx.Response:
        nonlocal reads
        body = json.loads(request.content)
        if body["method"] == "tasks/get":
            return response(task(1, "old reply"))
        assert body["method"] == "tasks/list"
        assert body["params"] == {"limit": 50}
        reads += 1
        if reads == 2:
            if outcome == "denied":
                return httpx.Response(403)
            if outcome == "malformed":
                return response({"tasks": "invalid"})
            return response({"tasks": [], "nextCursor": None})
        return response({"tasks": [task(reads)], "nextCursor": None})

    client = await client_for(serve)
    try:
        app = HistoryHost(client)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            await pilot.pause()
            screen = app.screen
            reply = screen.query_one("#history-reply", Static)
            assert "old reply" in str(reply.content)
            await pilot.press("r")
            await pilot.pause()
            assert reads == 2
            assert screen.query_one(DataTable).row_count == 0
            assert "old reply" not in str(reply.content)
            expected = "No tasks on this page." if outcome == "empty" else "Task history unavailable."
            assert str(reply.content) == expected
            await pilot.press("r")
            await pilot.pause()
            assert reads == 3
            assert str(screen.query_one(DataTable).get_cell_at((0, 1))) == "work-item:3"
    finally:
        await client.close()


async def test_pending_refresh_ignores_duplicate_refresh_and_selection() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    reads = 0

    async def serve(request: httpx.Request) -> httpx.Response:
        nonlocal reads
        body = json.loads(request.content)
        assert body["method"] == "tasks/list"
        assert body["params"] == {"limit": 50}
        reads += 1
        if reads == 2:
            entered.set()
            await release.wait()
        return response({"tasks": [task(reads)], "nextCursor": None})

    client = await client_for(serve)
    try:
        app = HistoryHost(client)
        async with app.run_test() as pilot:
            await pilot.press("r")
            await asyncio.wait_for(entered.wait(), timeout=2)
            assert app.screen.query_one(DataTable).row_count == 0
            await pilot.press("r", "r", "enter", "n")
            assert reads == 2
            release.set()
            await app.workers.wait_for_complete()
            assert str(app.screen.query_one(DataTable).get_cell_at((0, 1))) == "work-item:2"
    finally:
        release.set()
        await client.close()


@pytest.mark.parametrize("late_error", [False, True])
async def test_close_discards_refresh_completion_after_cancel(late_error: bool) -> None:
    entered = asyncio.Event()
    cancelled = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()
    reads = 0

    async def serve(request: httpx.Request) -> httpx.Response:
        nonlocal reads
        body = json.loads(request.content)
        assert body["method"] == "tasks/list"
        reads += 1
        if reads == 2:
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                await release.wait()
            completed.set()
            if late_error:
                return httpx.Response(403)
        return response({"tasks": [task(reads)], "nextCursor": None})

    client = await client_for(serve)
    client._current_session_id = "active-context"
    try:
        app = HistoryHost(client)
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, HistoryScreen)
            await pilot.press("r")
            await asyncio.wait_for(entered.wait(), timeout=2)
            reply = screen.query_one("#history-reply", Static)
            before = str(reply.content)
            await pilot.press("escape")
            await asyncio.wait_for(cancelled.wait(), timeout=2)
            assert app.screen is not screen
            await pilot.pause()
            release.set()
            await asyncio.wait_for(completed.wait(), timeout=2)
            await pilot.pause()
            assert screen.page == {"tasks": [], "nextCursor": None}
            assert str(reply.content) == before
            assert client.current_session_id == "active-context"
            assert reads == 2
    finally:
        release.set()
        await client.close()
