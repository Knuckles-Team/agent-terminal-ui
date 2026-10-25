"""Bounded source coverage, not installed producer or session/cost acceptance."""

from copy import deepcopy
import asyncio
import json
from typing import Any

import httpx
import pytest
from textual.app import App
from textual.widgets import Footer, Static

from agent_terminal_ui.app import AgentApp, AgentEventReceived
from agent_terminal_ui.client import AgentClient, normalize_a2a_event, task_turn_usage
from agent_terminal_ui.screens.main import MainScreen
from agent_terminal_ui.tui.history_screen import HistoryScreen
from agent_terminal_ui.tui.status_line import StatusLine

pytestmark = pytest.mark.spec("TUI-RUNTIME-R012.6.3")
MAX_COUNT = 9_007_199_254_740_991


def task() -> dict[str, Any]:
    return {
        "kind": "task", "id": "task-one", "contextId": "context-two",
        "status": {"state": "completed"},
        "metadata": {"arbora": {"runId": "run-three", "usage": {
            "taskId": "task-one", "contextId": "context-two", "runId": "run-three",
            "scope": "turn", "counts": {"requests": 1, "input_tokens": 17,
                                        "output_tokens": 0, "total_tokens": 17},
        }}},
        "artifacts": [{"parts": [{"kind": "text", "text": "Valid reply"}]}],
    }


def receipt(value: dict[str, Any]) -> dict[str, Any]:
    return value["metadata"]["arbora"]["usage"]


def test_normalizes_terminal_receipts_without_fabricating_missing_counters():
    value = task()
    receipt(value)["counts"]["input_tokens"] = MAX_COUNT
    for kind in ("task", "status-update"):
        event = deepcopy(value)
        event["kind"] = kind
        if kind == "status-update":
            event["taskId"] = event.pop("id")
            event["final"] = True
        usage = normalize_a2a_event(event, "local-session")[-1]["usage"]
        assert usage == receipt(value)
        assert usage["counts"]["output_tokens"] == 0
        assert "tool_calls" not in usage["counts"]
        assert "estimated_cost_usd" not in usage
        assert "session" not in usage


@pytest.mark.parametrize("counts", [{}, {"requests": 0}, {"total_tokens": MAX_COUNT}])
def test_empty_zero_and_maximum_counts_are_valid(counts):
    value = task()
    receipt(value)["counts"] = counts
    assert task_turn_usage(value)["counts"] == counts


@pytest.mark.parametrize("invalid", [True, False, -1, 1.0, "1", None, [], {}, MAX_COUNT + 1])
def test_one_invalid_counter_refuses_the_whole_receipt(invalid):
    value = task()
    receipt(value)["counts"]["tool_calls"] = invalid
    assert task_turn_usage(value) == {"scope": "turn"}


@pytest.mark.parametrize("counts", [{"requests": 1, "cost": 0}, [], None, "zero"])
def test_malformed_or_unknown_counts_refuse(counts):
    value = task()
    receipt(value)["counts"] = counts
    assert task_turn_usage(value) == {"scope": "turn"}


@pytest.mark.parametrize("key", ["taskId", "contextId", "runId", "scope"])
@pytest.mark.parametrize("invalid", ["foreign", None, 1, ""])
def test_receipt_binding_is_exact(key, invalid):
    value = task()
    receipt(value)[key] = invalid
    assert task_turn_usage(value) == {"scope": "turn"}


@pytest.mark.parametrize("path", [("id",), ("contextId",), ("metadata", "arbora", "runId")])
def test_selected_task_binding_must_survive_readback(path):
    selected = task()
    value = deepcopy(selected)
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = "foreign"
    assert task_turn_usage(value, selected) == {"scope": "turn"}


@pytest.mark.parametrize("usage", [None, [], {}, {"status": "unavailable", "reason": "producer_unavailable"}])
def test_absent_and_refused_receipts_never_become_zero(usage):
    value = task()
    value["metadata"]["arbora"]["usage"] = usage
    assert normalize_a2a_event(value, "context-two")[-1]["usage"] == {"scope": "turn"}
    del value["metadata"]["arbora"]["usage"]
    assert task_turn_usage(value) == {"scope": "turn"}


def test_nonterminal_receipt_is_not_displayed_and_failed_turn_keeps_counts():
    value = task()
    value["status"]["state"] = "working"
    assert all("usage" not in event for event in normalize_a2a_event(value, "context-two"))
    assert task_turn_usage(value) == {"scope": "turn"}
    value["status"]["state"] = "failed"
    events = normalize_a2a_event(value, "context-two")
    assert [event["type"] for event in events] == ["sideband", "error", "turn_end"]
    assert events[-1]["usage"] == receipt(value)


@pytest.mark.asyncio
async def test_stream_binding_change_refuses_usage_even_if_receipt_self_matches():
    client = AgentClient()
    initial = task()
    initial["status"]["state"] = "working"
    changed = task()
    changed["metadata"]["arbora"]["runId"] = "foreign"
    receipt(changed)["runId"] = "foreign"

    async def results():
        yield initial
        yield changed

    try:
        events = [event async for event in client._follow_results(results(), "context-two")]
        assert events[-1]["type"] == "turn_end"
        assert events[-1]["usage"] == {"scope": "turn"}
        assert "public_run_invalid" in events[-1]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_mounted_status_replay_absence_new_turn_and_error_clear(app: AgentApp):
    async with app.run_test(size=(100, 35)):
        widget = app.query_one("#status-tokens", Static)
        screen = app.screen
        assert isinstance(screen, MainScreen)
        event = normalize_a2a_event(task(), "context-two")[-1]
        for _ in range(2):
            await app.on_agent_event_received(AgentEventReceived(event))
            assert "Turn tokens: 17 in, 0 out, 17 total" in str(widget.render())
            assert "Session usage: unavailable" in str(widget.render())
            assert "Cost: unavailable" in str(widget.render())
            assert app._last_usage == receipt(task())
        absent = task()
        absent["metadata"]["arbora"].pop("usage")
        await app.on_agent_event_received(AgentEventReceived(normalize_a2a_event(absent, "context-two")[-1]))
        assert "Turn usage: unavailable" in str(widget.render())
        await app.on_agent_event_received(AgentEventReceived(event))
        screen.start_processing()
        assert "17" not in str(widget.render())
        await app.on_agent_event_received(AgentEventReceived(event))
        await app.on_agent_event_received(AgentEventReceived({"type": "error", "message": "Read refused"}))
        assert "17" not in str(widget.render())


async def client_for(handler) -> AgentClient:
    client = AgentClient(bearer_token="fixture-token")
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers={"Authorization": "Bearer fixture-token"}
    )
    client._current_session_id = "active-context"
    return client


def response(value):
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": "read", "result": value})


@pytest.mark.asyncio
async def test_fresh_client_history_read_replaces_usage_and_preserves_active_context():
    calls = []
    value = task()
    outcomes = [value, value, {**value, "metadata": {"arbora": {"runId": "run-three"}}}, None]

    def serve(request):
        assert request.headers["Authorization"] == "Bearer fixture-token"
        assert request.url.path == "/a2a"
        body = json.loads(request.content)
        assert body == {"jsonrpc": "2.0", "id": "tasks/get", "method": "tasks/get", "params": {"id": "task-one"}}
        calls.append(body)
        current = outcomes[len(calls) - 1]
        if current is None:
            return httpx.Response(403, json={"error": {"code": -32001, "message": "refused"}})
        return response(current)

    client = await client_for(serve)

    class Host(App):
        def on_mount(self):
            self.push_screen(HistoryScreen(client, {"tasks": [task()]}))

    host = Host()
    async with host.run_test(size=(100, 35)) as pilot:
        for index in range(4):
            await pilot.press("enter")
            await pilot.pause()
            usage = str(host.screen.query_one("#history-usage", Static).content)
            reply = str(host.screen.query_one("#history-reply", Static).content)
            if index < 2:
                for expected in ("Requests: 1", "Tool calls: unavailable", "Input tokens: 17", "Output tokens: 0", "Total tokens: 17"):
                    assert expected in usage
                assert "Valid reply" == reply
            else:
                assert "Turn usage: unavailable" in usage
                assert "17" not in usage
                assert reply == ("Valid reply" if index == 2 else "Task reply unavailable.")
            assert "Session usage: unavailable" in usage
            assert "Cost: unavailable" in usage
            assert client.current_session_id == "active-context"
            assert client.current_task_id is None
    assert len(calls) == 4
    await client.close()


@pytest.mark.asyncio
async def test_history_read_changed_run_preserves_reply_but_refuses_usage():
    value = task()
    value["metadata"]["arbora"]["runId"] = "foreign"
    receipt(value)["runId"] = "foreign"
    client = await client_for(lambda _: response(value))

    class Host(App):
        def on_mount(self):
            self.push_screen(HistoryScreen(client, {"tasks": [task()]}))

    host = Host()
    async with host.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        assert str(host.screen.query_one("#history-reply", Static).content) == "Valid reply"
        assert "Turn usage: unavailable" in str(host.screen.query_one("#history-usage", Static).content)
    await client.close()


@pytest.mark.asyncio
async def test_history_close_ignores_late_read_even_when_cancellation_is_suppressed():
    entered, finish = asyncio.Event(), asyncio.Event()

    async def serve(_):
        entered.set()
        try:
            await finish.wait()
        except asyncio.CancelledError:
            await finish.wait()
        return response(task())

    client = await client_for(serve)

    class Host(App):
        def on_mount(self):
            self.push_screen(HistoryScreen(client, {"tasks": [task()]}))

    host = Host()
    async with host.run_test() as pilot:
        screen = host.screen
        await pilot.press("enter")
        await asyncio.wait_for(entered.wait(), 2)
        await pilot.press("escape")
        finish.set()
        await pilot.pause()
        assert host.screen is not screen
        assert client.current_session_id == "active-context"
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["completed", "failed", "canceled"])
async def test_served_poll_receipt_reaches_mounted_status_without_additional_usage_read(app: AgentApp, terminal: str):
    calls = []

    def serve(request):
        assert request.url.path == "/a2a"
        assert request.headers["Authorization"] == "Bearer fixture-token"
        body = json.loads(request.content)
        calls.append(body)
        value = task()
        value["status"]["state"] = "submitted" if body["method"] == "message/send" else terminal
        if body["method"] == "message/send":
            assert body["params"]["configuration"] == {"blocking": False}
            value["metadata"]["arbora"].pop("usage")
        else:
            assert body["method"] == "tasks/get"
            assert body["params"] == {"id": "task-one"}
        return response(value)

    client = await client_for(serve)
    client._streaming = False
    client.poll_interval = 0
    try:
        async with app.run_test(size=(80, 35)):
            events = [event async for event in client.stream("Read receipt", session_id="context-two")]
            for event in events:
                await app.on_agent_event_received(AgentEventReceived(event))
            assert events[-1]["usage"] == receipt(task())
            assert "Turn tokens: 17 in, 0 out, 17 total" in str(app.query_one("#status-tokens", Static).render())
            assert [call["method"] for call in calls] == ["message/send", "tasks/get"]
    finally:
        await client.close()


@pytest.mark.parametrize("change", ["missing_run", "conflicting_task_id", "missing_kind", "invalid_context", "nonfinal"])
def test_malformed_envelope_refuses_without_partial_counts(change):
    value = task()
    if change == "missing_run":
        value["metadata"]["arbora"].pop("runId")
    elif change == "conflicting_task_id":
        value["taskId"] = "other-task"
    elif change == "missing_kind":
        value.pop("kind")
    elif change == "invalid_context":
        value["contextId"] = "invalid\ncontext"
        receipt(value)["contextId"] = value["contextId"]
    else:
        value["final"] = False
    assert task_turn_usage(value) == {"scope": "turn"}


@pytest.mark.asyncio
@pytest.mark.parametrize("counts", [{"input_tokens": 17, "output_tokens": 0, "total_tokens": 17}, {}, {"total_tokens": MAX_COUNT}])
async def test_turn_usage_resize_preserves_exact_details_without_footer_overlap(app: AgentApp, counts):
    value = task()
    receipt(value)["counts"] = counts
    async with app.run_test(size=(120, 35)) as pilot:
        await app.on_agent_event_received(AgentEventReceived(normalize_a2a_event(value, "context-two")[-1]))
        status = app.query_one(StatusLine)
        widget = app.query_one("#status-tokens", Static)
        for width, height in [(120, 35), (80, 24), (60, 20), (40, 12), (120, 35)]:
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            assert status.region.bottom <= app.query_one(Footer).region.y
            assert "Session usage: unavailable" in str(widget.tooltip)
            assert "Cost: unavailable" in str(widget.tooltip)
            assert f"Total tokens: {counts.get('total_tokens', 'unavailable')}" in str(widget.tooltip)
        assert "Turn tokens:" in str(widget.render())
        assert "Session usage: unavailable" in str(widget.render())
