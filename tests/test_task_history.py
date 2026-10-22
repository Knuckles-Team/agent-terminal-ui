"""Caller task history is a read-only served projection, not conversation resume."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from textual.app import App
from textual.widgets import DataTable, Static

from agent_terminal_ui.client import AgentClient, A2ATransportError
from agent_terminal_ui.commands import CommandProcessor
from agent_terminal_ui.tui.history_screen import HistoryScreen, task_reply

pytestmark = pytest.mark.asyncio


def task(number, reply=None):
    result = {
        "id": f"work-item:{number}",
        "contextId": f"context-{number}",
        "status": {"state": "completed", "timestamp": "2026-10-22T10:00:00Z"},
    }
    if reply is not None:
        result["artifacts"] = [{"parts": [{"kind": "text", "text": reply}]}]
    return result


async def client_for(handler):
    client = AgentClient()
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def response(result):
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": "read", "result": result})


@pytest.mark.spec("TUI-RUNTIME-R012.3.1")
async def test_pages_two_contexts_and_fresh_client_point_read():
    calls = []
    durable = task(1, "Persisted answer")

    def serve(request):
        assert request.url.path == "/a2a"
        body = json.loads(request.content)
        calls.append(body)
        if body["method"] == "tasks/list":
            assert body["params"] == {"limit": 50}
            return response({"tasks": [task(1), task(2)], "nextCursor": "opaque"})
        assert body["method"] == "tasks/get"
        assert body["params"] == {"id": "work-item:1"}
        return response(durable)

    client = await client_for(serve)
    assert len((await client.list_history_tasks())["tasks"]) == 2
    await client.close()
    restarted = await client_for(serve)
    read = await restarted.get_history_task("work-item:1", "context-1")
    assert task_reply(read) == "Persisted answer"
    assert restarted.current_session_id is None
    assert restarted.current_task_id is None
    await restarted.close()
    assert [x["method"] for x in calls] == ["tasks/list", "tasks/get"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"tasks": {}},
        {"tasks": [task(1)] * 51},
        {"tasks": [task(1), task(1)]},
        {"tasks": [{"id": "x"}]},
        {"tasks": [], "nextCursor": ""},
        {"tasks": [], "nextCursor": "same"},
    ],
)
@pytest.mark.spec("TUI-RUNTIME-R012.3.1")
async def test_invalid_pages_refuse(payload):
    client = await client_for(lambda _: response(payload))
    with pytest.raises(ValueError):
        await client.list_history_tasks("same")
    await client.close()


@pytest.mark.parametrize("result", [task(2), {**task(1), "contextId": "foreign"}, {}])
@pytest.mark.spec("TUI-RUNTIME-R012.3.1")
async def test_selected_identity_mismatch_refuses(result):
    client = await client_for(lambda _: response(result))
    with pytest.raises(ValueError):
        await client.get_history_task("work-item:1", "context-1")
    await client.close()


@pytest.mark.parametrize("code", [-32001, -32601, -32014])
@pytest.mark.spec("TUI-RUNTIME-R012.3.1")
async def test_owner_unknown_and_unavailable_refuse_without_context_change(code):
    calls = []

    def serve(request):
        calls.append(request)
        return httpx.Response(403, json={"error": {"code": code, "message": "refused"}})

    client = await client_for(serve)
    client._current_session_id = "active"
    with pytest.raises(A2ATransportError):
        await client.get_history_task("work-item:1", "context-1")
    assert client.current_session_id == "active"
    assert len(calls) == 1
    app = MagicMock()
    app._client = client
    await CommandProcessor(app).cmd_history("")
    app.notify.assert_called_once_with("Task history unavailable.", severity="warning")
    app.push_screen.assert_not_called()
    await client.close()


@pytest.mark.spec("TUI-RUNTIME-R012.3.1")
async def test_mounted_browser_pagination_selection_and_no_resume():
    calls = []

    def serve(request):
        body = json.loads(request.content)
        calls.append(body)
        if body["method"] == "tasks/list":
            assert body["params"] == {"limit": 50, "cursor": "opaque"}
            return response({"tasks": [task(2)], "nextCursor": None})
        assert body["method"] == "tasks/get"
        return response(task(2, "[red]literal reply[/red]"))

    client = await client_for(serve)
    client._current_session_id = "active-context"

    class Host(App):
        def on_mount(self):
            self.push_screen(
                HistoryScreen(client, {"tasks": [task(1)], "nextCursor": "opaque"})
            )

    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        await pilot.press("n")
        await pilot.pause()
        assert screen.query_one(DataTable).row_count == 1
        await pilot.press("enter")
        await pilot.pause()
        assert (
            str(screen.query_one("#history-reply", Static).content)
            == "[red]literal reply[/red]"
        )
        assert client.current_session_id == "active-context"
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is not screen
    assert [x["method"] for x in calls] == ["tasks/list", "tasks/get"]
    await client.close()


@pytest.mark.spec("TUI-RUNTIME-R012.3.1")
async def test_empty_page_keeps_cursor_and_refused_reply_clears_old_content():
    count = 0

    def serve(request):
        nonlocal count
        body = json.loads(request.content)
        if body["method"] == "tasks/list":
            return response({"tasks": [task(1)], "nextCursor": None})
        count += 1
        if count == 1:
            return response(task(1, "old reply"))
        return httpx.Response(
            404, json={"error": {"code": -32001, "message": "Task not found"}}
        )

    client = await client_for(serve)

    class Host(App):
        def on_mount(self):
            self.push_screen(
                HistoryScreen(client, {"tasks": [], "nextCursor": "empty-page"})
            )

    app = Host()
    async with app.run_test() as pilot:
        await pilot.press("n")
        await pilot.pause()
        screen = app.screen
        await screen.on_data_table_row_selected(SimpleNamespace(cursor_row=0)).wait()
        assert str(screen.query_one("#history-reply", Static).content) == "old reply"
        await screen.on_data_table_row_selected(SimpleNamespace(cursor_row=0)).wait()
        assert (
            str(screen.query_one("#history-reply", Static).content)
            == "Task reply unavailable."
        )
    await client.close()


@pytest.mark.parametrize(
    "artifacts",
    [
        None,
        [],
        [{"parts": [{"kind": "file"}]}],
        [{"parts": [{"kind": "text", "text": 42}]}],
    ],
)
@pytest.mark.spec("TUI-RUNTIME-R012.3.1")
async def test_missing_or_invalid_reply_is_not_empty_success(artifacts):
    assert task_reply({"artifacts": artifacts}) == "Reply unavailable."


@pytest.mark.spec("TUI-RUNTIME-R012.3.1")
async def test_close_cancels_pending_read_and_preserves_active_context():
    import asyncio

    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def serve(request):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    client = await client_for(serve)
    client._current_session_id = "active"

    class Host(App):
        def on_mount(self):
            self.push_screen(HistoryScreen(client, {"tasks": [task(1)]}))

    app = Host()
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await asyncio.wait_for(entered.wait(), timeout=2)
        await pilot.press("escape")
        await pilot.pause()
        await asyncio.wait_for(cancelled.wait(), timeout=2)
        assert not isinstance(app.screen, HistoryScreen)
        assert client.current_session_id == "active"
    await client.close()


@pytest.mark.spec("TUI-RUNTIME-R012.3.1")
async def test_cursor_cycle_refuses_without_repeat_request():
    calls = []

    def serve(request):
        calls.append(json.loads(request.content))
        return response({"tasks": [task(2)], "nextCursor": "two"})

    client = await client_for(serve)

    class Host(App):
        def on_mount(self):
            self.push_screen(
                HistoryScreen(client, {"tasks": [task(1)], "nextCursor": "one"})
            )

    app = Host()
    async with app.run_test() as pilot:
        await pilot.press("n")
        await pilot.pause()
        screen = app.screen
        screen.page["nextCursor"] = "one"
        await pilot.press("n")
        await pilot.pause()
        assert len(calls) == 1
    await client.close()
