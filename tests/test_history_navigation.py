"""Mounted cursor navigation against HTTP fixtures, not live resume evidence."""

import asyncio
import json

import httpx
import pytest
from textual.widgets import DataTable, Static

from tests.test_history_refresh import HistoryHost
from tests.test_task_history import client_for, response, task

pytestmark = [pytest.mark.asyncio, pytest.mark.spec("TUI-RUNTIME-R012.3.1.1")]


async def test_previous_rereads_opaque_cursors_and_refresh_resets_path() -> None:
    calls = []
    visits = {None: 0, "opaque/a": 0, "opaque/b": 0}

    def serve(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["method"] == "tasks/list"
        cursor = body["params"].get("cursor")
        calls.append(cursor)
        visits[cursor] += 1
        number = {None: 1, "opaque/a": 2, "opaque/b": 3}[cursor]
        current = task(number)
        current["status"]["state"] = f"visit-{visits[cursor]}"
        return response({"tasks": [current], "nextCursor": {None: "opaque/a", "opaque/a": "opaque/b", "opaque/b": None}[cursor]})

    client = await client_for(serve)
    client._current_session_id = "active"
    try:
        app = HistoryHost(client)
        async with app.run_test() as pilot:
            await pilot.press("p")
            assert calls == [None]
            await pilot.press("n", "n", "p")
            await pilot.pause()
            table = app.screen.query_one(DataTable)
            assert str(table.get_cell_at((0, 1))) == "work-item:2"
            assert str(table.get_cell_at((0, 3))) == "visit-2"
            await pilot.press("n", "p", "p")
            await pilot.pause()
            assert str(table.get_cell_at((0, 1))) == "work-item:1"
            await pilot.press("n", "r", "p")
            await pilot.pause()
            assert calls == [None, "opaque/a", "opaque/b", "opaque/a", "opaque/b", "opaque/a", None, "opaque/a", None]
            assert client.current_session_id == "active"
            assert client.current_task_id is None
    finally:
        await client.close()


@pytest.mark.parametrize("outcome", ["denied", "malformed", "empty"])
async def test_previous_clears_old_content_and_retries(outcome: str) -> None:
    reads = 0

    def serve(request: httpx.Request) -> httpx.Response:
        nonlocal reads
        body = json.loads(request.content)
        if body["method"] == "tasks/get":
            return response(task(2, "old reply"))
        reads += 1
        if reads == 3:
            if outcome == "denied":
                return httpx.Response(403)
            if outcome == "malformed":
                return response({"tasks": "invalid"})
            return response({"tasks": [], "nextCursor": "opaque"})
        cursor = body["params"].get("cursor")
        return response({"tasks": [task(2 if cursor else 1)], "nextCursor": None if cursor else "opaque"})

    client = await client_for(serve)
    try:
        app = HistoryHost(client)
        async with app.run_test() as pilot:
            await pilot.press("n", "enter", "p")
            await pilot.pause()
            screen = app.screen
            assert screen.query_one(DataTable).row_count == 0
            reply = str(screen.query_one("#history-reply", Static).content)
            assert "old reply" not in reply
            assert reply == ("No tasks on this page." if outcome == "empty" else "Task history unavailable.")
            await pilot.press("n" if outcome == "empty" else "p")
            await pilot.pause()
            assert reads == 4
            assert screen.query_one(DataTable).row_count == 1
    finally:
        await client.close()


@pytest.mark.parametrize("key", ["n", "p"])
@pytest.mark.parametrize("late_error", [False, True])
async def test_navigation_ignores_duplicates_and_discards_closed_completion(key: str, late_error: bool) -> None:
    entered, cancelled, release, completed = (asyncio.Event() for _ in range(4))
    calls = []
    blocked = False

    async def serve(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["method"] == "tasks/list"
        cursor = body["params"].get("cursor")
        calls.append(cursor)
        if blocked:
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                await release.wait()
            completed.set()
            if late_error:
                return httpx.Response(403)
        return response({"tasks": [task(2 if cursor else 1)], "nextCursor": None if cursor else "opaque"})

    client = await client_for(serve)
    try:
        app = HistoryHost(client)
        async with app.run_test() as pilot:
            if key == "p":
                await pilot.press("n")
                await pilot.pause()
            blocked = True
            screen = app.screen
            await pilot.press(key)
            await asyncio.wait_for(entered.wait(), 2)
            assert screen.query_one(DataTable).row_count == 0
            before = len(calls)
            await pilot.press("n", "p", "r", "enter")
            assert len(calls) == before
            reply = screen.query_one("#history-reply", Static)
            content = str(reply.content)
            page = screen.page.copy()
            await pilot.press("escape")
            await asyncio.wait_for(cancelled.wait(), 2)
            release.set()
            await asyncio.wait_for(completed.wait(), 2)
            await pilot.pause()
            assert app.screen is not screen
            assert screen.page == page
            assert str(reply.content) == content
    finally:
        release.set()
        await client.close()


async def test_failed_next_retries_and_cyclic_cursor_does_not_advance() -> None:
    calls = []
    attempts = 0

    def serve(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        body = json.loads(request.content)
        assert body["method"] == "tasks/list"
        cursor = body["params"].get("cursor")
        calls.append(cursor)
        if cursor == "second":
            attempts += 1
            if attempts == 1:
                return httpx.Response(403)
        next_cursor = {None: "first", "first": "second", "second": "first"}[cursor]
        return response({"tasks": [task(len(calls))], "nextCursor": next_cursor})

    client = await client_for(serve)
    try:
        app = HistoryHost(client)
        async with app.run_test() as pilot:
            await pilot.press("n", "n")
            await pilot.pause()
            screen = app.screen
            assert screen.query_one(DataTable).row_count == 0
            assert str(screen.query_one("#history-reply", Static).content) == "Task history unavailable."
            await pilot.press("n")
            await pilot.pause()
            assert screen.query_one(DataTable).row_count == 0
            await pilot.press("p")
            await pilot.pause()
            assert calls == [None, "first", "second", "second", None]
            assert screen.query_one(DataTable).row_count == 1
    finally:
        await client.close()
