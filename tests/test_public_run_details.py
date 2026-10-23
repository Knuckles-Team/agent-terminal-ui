"""Shared public projection and mounted inline fold acceptance."""

import asyncio
import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input

from agent_terminal_ui.client import (
    A2ATransportError,
    AgentClient,
    ArboraOperationError,
    normalize_a2a_event,
)
from agent_terminal_ui.public_run_events import (
    MAX_VIEW_BYTES,
    PublicRunEvent,
    PublicRunPage,
)
from agent_terminal_ui.widgets.conversation import Conversation
from agent_terminal_ui.widgets.public_run_details import PublicRunDetails

pytestmark = pytest.mark.spec("TUI-RUNTIME-R008.2.3.2.2.1")


def page():
    return json.loads(
        (Path(__file__).parent / "fixtures/public_run_events.json").read_text()
    )


def binding():
    return {"task_id": "task-1", "context_id": "context-1", "run_id": "run-1"}


def test_public_projection_never_renders_unrecognized_private_fields():
    value = page()
    for event in value["events"]:
        event["reasoning"] = "private sentinel"
        event["payload"]["thought"] = "private sentinel"
        event["payload"]["output"] = "private sentinel"
    value["events"][1]["payload"]["summary"] += "\x1b\x07\u202e\u2066\ud800\u061c\u200f"
    parsed = PublicRunPage.parse(value, "run-1", 0)
    text = str(parsed)
    assert "private sentinel" not in text
    assert "[bold]literal[/bold]" in text
    assert "\\x1b" not in text and "\\u202e" not in text
    assert "\\ud800" not in text and "\\u200f" not in text
    assert parsed.events[1].text.encode()
    assert parsed.terminal and parsed.next_after == 5


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(run_id="foreign"),
        lambda p: p.update(schema_version="unknown"),
        lambda p: p.update(after=True),
        lambda p: p.update(next_after=6),
        lambda p: p.update(terminal=False),
        lambda p: p.update(has_more=True),
        lambda p: p["events"][0].update(run_id="foreign"),
        lambda p: p["events"][0].update(sequence=True),
        lambda p: p["events"][0].update(sequence=2),
        lambda p: p["events"][0].update(type="reasoning"),
        lambda p: p["events"][0].update(category="public_summary"),
        lambda p: p["events"][1].update(event_id=p["events"][0]["event_id"]),
        lambda p: p["events"][1]["payload"].update(summary="x" * 16_385),
    ],
)
def test_public_projection_rejects_invalid_or_foreign_pages(mutate):
    value = page()
    mutate(value)
    with pytest.raises(ValueError):
        PublicRunPage.parse(value, "run-1", 0)


class DetailsApp(App):
    def __init__(self, client, task_id="task-1"):
        super().__init__()
        self.client = client
        self.task_id = task_id
        self.submissions = 0

    def compose(self) -> ComposeResult:
        yield Conversation()
        yield Input()

    async def on_mount(self):
        conversation = self.query_one(Conversation)
        await conversation.add_user_message("Compare my options")
        await conversation.bind_public_run(
            self.client, {**binding(), "task_id": self.task_id}
        )
        await conversation.add_agent_response("The answer remains visible.")

    def on_input_submitted(self):
        self.submissions += 1


@pytest.mark.asyncio
async def test_inline_folds_are_lazy_and_keyboard_accessible_with_focus_and_replay():
    client = AsyncMock(spec=AgentClient)
    client.get_public_run_events.return_value = page()
    app = DetailsApp(client)
    async with app.run_test(size=(100, 40)) as pilot:
        details = app.query_one(PublicRunDetails)
        client.get_public_run_events.assert_not_called()
        assert details.summary_fold.collapsed and details.trace_fold.collapsed
        header = details.summary_fold.query_one("CollapsibleTitle")
        header.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert not details.summary_fold.collapsed and details.trace_fold.collapsed
        assert app.focused is header and app.submissions == 0
        assert "Public explanation:" in str(details._summary.render())
        assert "[bold]literal[/bold]" in str(details._summary.render())
        assert "task_started" in str(details._trace.render())
        await pilot.press("space")
        assert details.summary_fold.collapsed
        trace_header = details.trace_fold.query_one("CollapsibleTitle")
        trace_header.focus()
        await pilot.press("enter")
        details.action_replay()
        await pilot.pause()
        assert app.focused is trace_header
        assert details.summary_fold.collapsed and not details.trace_fold.collapsed
        assert len(details.records) == 5 and app.submissions == 0
        await pilot.click(header)
        assert not details.summary_fold.collapsed
        assert len(app.query(PublicRunDetails)) == 1


@pytest.mark.asyncio
async def test_inline_read_preserves_opaque_owner_task_distinct_from_run():
    client = AsyncMock(spec=AgentClient)
    client.get_public_run_events.return_value = page()
    task_id = "work-item:" + "a" * 64
    async with DetailsApp(client, task_id).run_test(size=(100, 40)) as pilot:
        details = pilot.app.query_one(PublicRunDetails)
        details.trace_fold.query_one("CollapsibleTitle").focus()
        await pilot.press("enter")
        await pilot.pause()
        client.get_public_run_events.assert_awaited_once_with(
            "run-1", task_id=task_id, after=0
        )
        assert details.terminal and "task_started" in str(details._trace.render())


@pytest.mark.asyncio
async def test_refusal_and_changed_task_binding_clear_content_without_expanding():
    client = AsyncMock(spec=AgentClient)
    client.get_public_run_events.return_value = page()
    app = DetailsApp(client)
    async with app.run_test(size=(100, 40)) as pilot:
        details = app.query_one(PublicRunDetails)
        details.trace_fold.collapsed = False
        await pilot.pause()
        assert "task_started" in str(details._trace.render())
        client.get_public_run_events.side_effect = ArboraOperationError(
            "ACCESS_DENIED", {"detail": "private transport detail"}
        )
        details.POLL_INTERVAL = 0.01
        details.action_replay()
        await pilot.pause()
        assert details.summary_fold.collapsed and not details.trace_fold.collapsed
        assert "task_started" not in str(details._trace.render())
        assert "private" not in str(details._trace.render())
        assert "unavailable" in str(details._summary.render())
        await asyncio.sleep(0.05)
        assert client.get_public_run_events.await_count == 2
        await app.query_one(Conversation).bind_public_run(
            client, {**binding(), "run_id": "other-run"}
        )
        assert not details._valid and not details.records
        assert len(app.query(PublicRunDetails)) == 1


@pytest.mark.asyncio
async def test_existing_client_uses_registered_operation_with_exact_run_cursor(
    monkeypatch,
):
    client = AgentClient()
    invoke = AsyncMock(return_value={"value": page()})
    monkeypatch.setattr(client, "invoke_op", invoke)
    assert (
        await client.get_public_run_events("run-1", task_id="work-item:owner", after=0)
        == page()
    )
    invoke.assert_awaited_once_with(
        "runs.events",
        {"run_id": "run-1", "task_id": "work-item:owner", "after": 0, "limit": 1000},
    )
    for run, after in [("", 0), ("bad\x1b", 0), ("run-1", True), ("run-1", -1)]:
        with pytest.raises(ValueError):
            await client.get_public_run_events(
                run, task_id="work-item:owner", after=after
            )
    invalid_tasks: list[Any] = ["", "bad\x1b", "x" * 513, 12]
    for task in invalid_tasks:
        with pytest.raises(ValueError):
            await client.get_public_run_events("run-1", task_id=task)
    assert invoke.await_count == 1
    await client._http_client.aclose()


def test_normalizer_requires_server_task_context_and_run_before_inline_read():
    task = {
        "kind": "task",
        "id": "task-1",
        "contextId": "context-1",
        "status": {"state": "working"},
        "metadata": {"arbora": {"runId": "run-1"}},
    }
    assert normalize_a2a_event(task, "context-1")[0]["public_run_binding"] == binding()
    for field, invalid in [("kind", "not-a-task"), ("status", {"state": "unknown"})]:
        bad = {**task, field: invalid}
        normalized = normalize_a2a_event(bad, "context-1")[0]
        assert "public_run_binding" not in normalized
        assert "public_task_binding" not in normalized
    status_update = {**task, "kind": "status-update", "taskId": "task-1"}
    status_update.pop("id")
    assert (
        normalize_a2a_event(status_update, "context-1")[0]["public_run_binding"]
        == binding()
    )
    for key in ["id", "contextId", "metadata"]:
        bad = copy.deepcopy(task)
        bad.pop(key)
        assert "public_run_binding" not in normalize_a2a_event(bad, "context-1")[0]


@pytest.mark.asyncio
async def test_production_app_routes_bound_task_to_inline_folds_without_submitting(
    app, fake_client
):
    from agent_terminal_ui.app import AgentEventReceived
    from agent_terminal_ui.tui.input_text_area import InputTextArea

    fake_client.get_public_run_events.return_value = page()
    task = {
        "kind": "task",
        "id": "task-1",
        "contextId": "context-1",
        "status": {"state": "working"},
        "metadata": {"arbora": {"runId": "run-1"}},
    }
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app._run_agent_turn = AsyncMock()
        for event in normalize_a2a_event(task, "context-1"):
            await app.on_agent_event_received(AgentEventReceived(event))
        await pilot.pause()
        details = app.query_one(PublicRunDetails)
        fake_client.get_public_run_events.assert_not_awaited()
        details.summary_fold.query_one("CollapsibleTitle").focus()
        await pilot.press("enter")
        await pilot.pause()
        assert "Public explanation:" in str(details._summary.render())
        assert not details.summary_fold.collapsed and details.trace_fold.collapsed
        assert app.query_one(InputTextArea).text == ""
        app._run_agent_turn.assert_not_called()
        fake_client.cancel_task.assert_not_called()


@pytest.mark.asyncio
async def test_transport_binding_conflict_invalidates_original_details():
    client = AgentClient()
    first: dict[str, Any] = {
        "kind": "task",
        "id": "task-1",
        "contextId": "context-1",
        "status": {"state": "working"},
        "metadata": {"arbora": {"runId": "run-1"}},
    }
    second = copy.deepcopy(first)
    second["metadata"]["arbora"]["runId"] = "foreign-run"

    async def results():
        yield first
        yield second

    received = [event async for event in client._follow_results(results(), "context-1")]
    assert received[0]["public_run_binding"] == binding()
    assert received[1]["public_run_invalid"] == binding()
    assert "public_run_binding" not in received[1]
    await client._http_client.aclose()


@pytest.mark.asyncio
async def test_cancelled_slow_read_cannot_restore_old_content():
    client = AsyncMock(spec=AgentClient)
    started = asyncio.Event()

    async def late(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return page()

    client.get_public_run_events.side_effect = late
    app = DetailsApp(client)
    async with app.run_test(size=(100, 40)) as pilot:
        details = app.query_one(PublicRunDetails)
        details.trace_fold.collapsed = False
        await started.wait()
        details.invalidate()
        await pilot.pause()
        assert not details.records
        assert "task_started" not in str(details._trace.render())


@pytest.mark.asyncio
async def test_task_only_placeholder_keeps_choice_when_run_binding_arrives():
    client = AsyncMock(spec=AgentClient)
    client.get_public_run_events.return_value = page()
    app = DetailsApp(client)
    async with app.run_test(size=(100, 40)) as pilot:
        conversation = app.query_one(Conversation)
        partial = {"task_id": "legacy-task", "context_id": "legacy-context"}
        await conversation.bind_public_run(client, partial)
        details = list(app.query(PublicRunDetails))[-1]
        header = details.summary_fold.query_one("CollapsibleTitle")
        header.focus()
        await pilot.press("enter")
        assert not details.summary_fold.collapsed
        assert "unavailable" in str(details._summary.render())
        client.get_public_run_events.assert_not_called()
        await conversation.bind_public_run(client, {**partial, "run_id": "run-1"})
        await pilot.pause()
        assert app.focused is header and not details.summary_fold.collapsed
        assert "Public explanation:" in str(details._summary.render())
        client.get_public_run_events.assert_awaited_once_with(
            "run-1", task_id="legacy-task", after=0
        )


@pytest.mark.asyncio
async def test_incremental_pages_and_transient_reconnect_keep_user_selected_folds():
    value = page()
    first = {
        **value,
        "events": value["events"][:2],
        "next_after": 2,
        "terminal": False,
        "has_more": True,
    }
    second = {**value, "after": 2, "events": value["events"][2:]}
    client = AsyncMock(spec=AgentClient)
    client.get_public_run_events.side_effect = [
        first,
        RuntimeError("disconnected"),
        first,
        second,
    ]
    app = DetailsApp(client)
    async with app.run_test(size=(100, 40)) as pilot:
        details = app.query_one(PublicRunDetails)
        details.POLL_INTERVAL = 0.01
        header = details.trace_fold.query_one("CollapsibleTitle")
        header.focus()
        await pilot.press("enter")
        for _ in range(30):
            await asyncio.sleep(0.01)
            if details.terminal:
                break
        assert details.terminal and len(details.records) == 5
        assert details.summary_fold.collapsed and not details.trace_fold.collapsed
        assert app.focused is header and app.submissions == 0
        assert [
            call.kwargs["after"]
            for call in client.get_public_run_events.await_args_list
        ] == [0, 2, 0, 2]


def test_public_details_retention_bounds_count_and_display_bytes():
    details = PublicRunDetails(AsyncMock(spec=AgentClient), "run-1", "task-1")
    records = tuple(
        PublicRunEvent(
            str(index),
            index,
            "run-1",
            "task-1",
            "public_summary",
            "x" * 16_384,
            "x" * 16_384,
            False,
        )
        for index in range(1, 1001)
    )
    details.apply_page(PublicRunPage(records, 1000, False, False))
    assert len(details.records) == 8
    assert sum(len(event.text.encode()) for event in details.records) == MAX_VIEW_BYTES
    assert details.next_after == 1000


@pytest.mark.asyncio
async def test_replay_while_both_folds_are_collapsed_stays_lazy():
    client = AsyncMock(spec=AgentClient)
    client.get_public_run_events.return_value = page()
    app = DetailsApp(client)
    async with app.run_test() as pilot:
        details = app.query_one(PublicRunDetails)
        details.action_replay()
        await pilot.pause()
        client.get_public_run_events.assert_not_called()
        details.trace_fold.collapsed = False
        await pilot.pause()
        details.trace_fold.collapsed = True
        await pilot.pause()
        details.action_replay()
        await pilot.pause()
        assert client.get_public_run_events.await_count == 1
        assert not details.records and not details._reading


@pytest.mark.asyncio
async def test_cross_page_duplicate_event_id_clears_without_changing_folds():
    value = page()
    first = {
        **value,
        "events": value["events"][:2],
        "next_after": 2,
        "terminal": False,
        "has_more": True,
    }
    second = {**value, "after": 2, "events": copy.deepcopy(value["events"][2:])}
    second["events"][0]["event_id"] = first["events"][0]["event_id"]
    client = AsyncMock(spec=AgentClient)
    client.get_public_run_events.side_effect = [first, second]
    app = DetailsApp(client)
    async with app.run_test() as pilot:
        details = app.query_one(PublicRunDetails)
        details.trace_fold.collapsed = False
        await pilot.pause()
        assert not details.records and not details._reading
        assert details.summary_fold.collapsed and not details.trace_fold.collapsed
        assert "unavailable" in str(details._trace.render())
        assert client.get_public_run_events.await_count == 2


@pytest.mark.parametrize(
    "kind,key,alias", [("task", "id", "taskId"), ("status-update", "taskId", "id")]
)
def test_public_binding_rejects_missing_kind_key_and_conflicting_aliases(
    kind, key, alias
):
    task = {
        "kind": kind,
        key: "task-1",
        "contextId": "context-1",
        "status": {"state": "working"},
        "metadata": {"arbora": {"runId": "run-1"}},
    }
    for invalid in [
        {**task, alias: "foreign-task"},
        {**task, alias: "task-1", key: None},
    ]:
        result = normalize_a2a_event(invalid, "context-1")[0]
        assert (
            "public_run_binding" not in result and "public_task_binding" not in result
        )


@pytest.mark.asyncio
async def test_unchanged_working_poll_still_invalidates_foreign_binding(monkeypatch):
    client = AgentClient()
    client._streaming = False
    client.poll_interval = 0
    first = {
        "kind": "task",
        "id": "task-1",
        "contextId": "context-1",
        "status": {"state": "working"},
        "metadata": {"arbora": {"runId": "run-1"}},
    }
    foreign = {**first, "metadata": {"arbora": {"runId": "foreign-run"}}}
    completed = {**foreign, "status": {"state": "completed"}}
    rpc = AsyncMock(side_effect=[first, foreign, completed])
    monkeypatch.setattr(client, "_rpc", rpc)
    received = [
        event async for event in client.stream("question", session_id="context-1")
    ]
    assert received[1]["data"]["state"] == "working"
    assert received[-1]["type"] == "error"
    assert received[-1]["public_run_invalid"] == binding()
    assert rpc.await_count == 2
    await client._http_client.aclose()


@pytest.mark.asyncio
async def test_stream_denial_after_binding_marks_details_invalid(monkeypatch):
    client = AgentClient()

    async def results(*_args):
        yield {
            "kind": "task",
            "id": "task-1",
            "contextId": "context-1",
            "status": {"state": "working"},
            "metadata": {"arbora": {"runId": "run-1"}},
        }
        raise A2ATransportError({"code": -32001}, status_code=403)

    monkeypatch.setattr(client, "_conversation_results", results)
    received = [
        event async for event in client.stream("question", session_id="context-1")
    ]
    assert received[-1]["type"] == "error"
    assert received[-1]["public_run_invalid"] == binding()
    await client._http_client.aclose()


@pytest.mark.asyncio
async def test_fresh_exact_binding_recovers_cleared_details_without_losing_choice():
    client = AsyncMock(spec=AgentClient)
    client.get_public_run_events.return_value = page()
    app = DetailsApp(client)
    async with app.run_test() as pilot:
        conversation = app.query_one(Conversation)
        details = app.query_one(PublicRunDetails)
        details.trace_fold.collapsed = False
        await pilot.pause()
        details.invalidate()
        assert not details._valid and not details.records
        details.action_replay()
        assert client.get_public_run_events.await_count == 1
        await conversation.bind_public_run(client, binding())
        await pilot.pause()
        assert details._valid and len(details.records) == 5
        assert details.summary_fold.collapsed and not details.trace_fold.collapsed
        assert client.get_public_run_events.await_count == 2


@pytest.mark.asyncio
async def test_resubscribe_denial_before_first_frame_invalidates_existing_task(
    monkeypatch,
):
    client = AgentClient()

    refused = AsyncMock(
        side_effect=A2ATransportError({"code": -32001}, status_code=403)
    )

    async def denied(*_args, **_kwargs):
        yield await refused()

    monkeypatch.setattr(client, "_rpc_stream", denied)
    received = []
    with pytest.raises(A2ATransportError):
        async for event in client.resubscribe("task-1"):
            received.append(event)
    assert received[0]["public_run_invalid"] == {"task_id": "task-1"}
    await client._http_client.aclose()


@pytest.mark.parametrize("transport", ["stream", "poll"])
@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"status": ["bad"]},
        {"status": "bad"},
        {"status": 1},
        {"status": {"state": []}},
    ]
    + [
        {"artifact": value}
        for value in (
            ["bad"],
            "bad",
            {"parts": 1},
            {"parts": [1]},
            {"parts": [{"kind": "text", "text": {"private": "never render"}}]},
        )
    ]
    + [{"history": value} for value in (1, "bad", [1])]
    + [{"artifacts": value} for value in (1, "bad", [1])],
)
@pytest.mark.asyncio
async def test_malformed_a2a_shapes_clear_bound_values_in_production_app(
    app, fake_client, monkeypatch, transport, invalid_fields
):
    from agent_terminal_ui.app import AgentEventReceived

    client = AgentClient()
    client.poll_interval = 0
    first = {
        "kind": "task",
        "id": "task-1",
        "contextId": "context-1",
        "status": {"state": "working"},
        "metadata": {"arbora": {"runId": "run-1"}},
    }
    bad = {**first, "status": {"state": "completed"}, **invalid_fields}
    if "artifact" in invalid_fields:
        if transport == "stream":
            bad = {
                "kind": "artifact-update",
                "taskId": "task-1",
                "contextId": "context-1",
                **invalid_fields,
            }
        else:
            bad = {**bad, "artifacts": [invalid_fields["artifact"]]}

    async def results(*_args, **_kwargs):
        yield first
        yield bad

    monkeypatch.setattr(
        client, "streaming_supported", AsyncMock(return_value=transport == "stream")
    )
    monkeypatch.setattr(client, "_rpc_stream", results)
    monkeypatch.setattr(client, "_rpc", AsyncMock(side_effect=[first, bad]))
    fake_client.get_public_run_events.return_value = page()
    try:
        async with app.run_test(size=(120, 50)) as pilot:
            received = []
            async for event in client.stream("question", session_id="context-1"):
                received.append(event)
                await app.on_agent_event_received(AgentEventReceived(event))
                if "public_run_binding" in event:
                    details = app.query_one(PublicRunDetails)
                    details.apply_page(PublicRunPage.parse(page(), "run-1", 0))
                    assert details.records
            await pilot.pause()
            assert received[-1]["public_run_invalid"] == binding()
            details = app.query_one(PublicRunDetails)
            assert not details._valid and not details.records
            assert "Public explanation:" not in str(details._summary.render())
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_resubscribe_rejects_foreign_first_frame_before_admitting_details(
    app, fake_client, monkeypatch
):
    from agent_terminal_ui.app import AgentEventReceived

    client = AgentClient()
    first = {
        "kind": "task",
        "id": "task-1",
        "contextId": "context-1",
        "status": {"state": "working"},
        "metadata": {"arbora": {"runId": "run-1"}},
    }

    async def foreign(*_args, **_kwargs):
        yield {
            **first,
            "id": "foreign-task",
            "contextId": "foreign-context",
            "metadata": {"arbora": {"runId": "foreign-run"}},
        }

    monkeypatch.setattr(client, "_rpc_stream", foreign)
    try:
        async with app.run_test(size=(120, 50)) as pilot:
            for event in normalize_a2a_event(first, "context-1"):
                await app.on_agent_event_received(AgentEventReceived(event))
            details = app.query_one(PublicRunDetails)
            details.apply_page(PublicRunPage.parse(page(), "run-1", 0))
            received = []
            with pytest.raises(ValueError, match="task target"):
                async for event in client.resubscribe("task-1"):
                    received.append(event)
                    await app.on_agent_event_received(AgentEventReceived(event))
            await pilot.pause()
            assert received[0]["public_run_invalid"] == {"task_id": "task-1"}
            assert not details._valid and not details.records
            assert len(app.query(PublicRunDetails)) == 1
            fake_client.get_public_run_events.assert_not_awaited()
            assert all("public_run_binding" not in event for event in received)
    finally:
        await client.close()


@pytest.mark.parametrize("failure", ["[]", "1", '"bad"', "error-shape", 401, 403, 500])
@pytest.mark.asyncio
async def test_malformed_sse_and_http_refusals_invalidate_bound_task(failure):
    task = {
        "kind": "task",
        "id": "task-1",
        "contextId": "context-1",
        "status": {"state": "working"},
        "metadata": {"arbora": {"runId": "run-1"}},
    }
    frame = {"jsonrpc": "2.0", "id": "fixture", "result": task}

    def response(request):
        if isinstance(failure, str):
            malformed = (
                json.dumps({**frame, "error": []})
                if failure == "error-shape"
                else failure
            )
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                text=f"data: {json.dumps(frame)}\n\ndata: {malformed}\n\n",
            )
        method = json.loads(request.content)["method"]
        return httpx.Response(200 if method == "message/send" else failure, json=frame)

    client = AgentClient()
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(response))
    client._streaming = isinstance(failure, str)
    client.poll_interval = 0
    try:
        received = [
            event async for event in client.stream("question", session_id="context-1")
        ]
        assert received[1]["public_run_binding"] == binding()
        assert received[-1]["type"] == "error"
        assert received[-1]["public_run_invalid"] == binding()
    finally:
        await client.close()


@pytest.mark.parametrize(
    "foreign_fields",
    [
        {"id": "foreign-task"},
        {"taskId": "foreign-alias"},
        {"contextId": "foreign-context"},
        {"metadata": {"arbora": {"runId": "foreign-run"}}},
    ],
)
@pytest.mark.asyncio
async def test_poll_validates_terminal_identity_before_extracting_answer(
    monkeypatch, foreign_fields
):
    task = {
        "kind": "task",
        "id": "task-1",
        "contextId": "context-1",
        "status": {"state": "working"},
        "metadata": {"arbora": {"runId": "run-1"}},
    }
    terminal = {
        **task,
        "status": {"state": "completed"},
        "artifacts": [{"parts": [{"kind": "text", "text": "Foreign answer"}]}],
        **foreign_fields,
    }
    client = AgentClient()
    client._streaming = False
    client.poll_interval = 0
    monkeypatch.setattr(client, "_rpc", AsyncMock(side_effect=[task, terminal]))
    try:
        received = [
            event async for event in client.stream("question", session_id="context-1")
        ]
        assert all(event["type"] != "text" for event in received)
        assert received[-1]["public_run_invalid"] == binding()
    finally:
        await client.close()


@pytest.mark.parametrize(
    "metadata",
    [None, [], {"arbora": None}, {"arbora": []}, {"arbora": {"runId": None}}],
)
@pytest.mark.asyncio
async def test_malformed_metadata_does_not_silently_retain_old_run(metadata):
    client = AgentClient()
    first = {
        "kind": "task",
        "id": "task-1",
        "contextId": "context-1",
        "status": {"state": "working"},
        "metadata": {"arbora": {"runId": "run-1"}},
    }

    async def results():
        yield first
        yield {**first, "metadata": metadata}

    received = [event async for event in client._follow_results(results(), "context-1")]
    assert received[-1]["public_run_invalid"] == binding()
    await client.close()


@pytest.mark.parametrize(
    "field,value", [("kind", []), ("status", {"state": []}), ("status", {"state": {}})]
)
def test_malformed_task_shapes_do_not_create_public_bindings(field, value):
    result = {
        "kind": "task",
        "id": "task-1",
        "contextId": "context-1",
        "status": {"state": "working"},
        "metadata": {"arbora": {"runId": "run-1"}},
    }
    result[field] = value
    if field == "status":
        with pytest.raises(ValueError, match="task state"):
            normalize_a2a_event(result, "context-1")
        return
    assert all(
        "public_run_binding" not in event and "public_task_binding" not in event
        for event in normalize_a2a_event(result, "context-1")
    )


@pytest.mark.asyncio
async def test_unknown_frame_kind_still_clears_previously_bound_details():
    client = AgentClient()
    first = {
        "kind": "task",
        "id": "task-1",
        "contextId": "context-1",
        "status": {"state": "working"},
        "metadata": {"arbora": {"runId": "run-1"}},
    }

    async def results():
        yield first
        yield {**first, "kind": "unknown"}

    received = [event async for event in client._follow_results(results(), "context-1")]
    assert received[-1]["public_run_invalid"] == binding()
    await client.close()


@pytest.mark.parametrize(
    "variant", ["available", "unavailable", "empty", "empty-terminal"]
)
@pytest.mark.asyncio
async def test_legacy_replay_refuses_new_projection_instead_of_false_empty_success(
    variant,
):
    value = page()
    if variant != "available":
        value["events"] = []
        value["next_after"] = None if variant == "unavailable" else 0
        value["terminal"] = variant == "empty-terminal"
    if variant == "unavailable":
        value["availability"] = "unavailable"
    client = AgentClient()
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=value))
    )
    with pytest.raises(ValueError, match="inline task details.*legacy schema"):
        await client.get_run_events("run-1")
    await client.close()


def test_resumed_empty_terminal_page_uses_cursor_without_inventing_events():
    value = page()
    value.update(events=[], after=5)
    parsed = PublicRunPage.parse(value, "run-1", 5)
    assert parsed.events == () and parsed.terminal and not parsed.has_more
    assert parsed.next_after == 5
    value["has_more"] = True
    with pytest.raises(ValueError):
        PublicRunPage.parse(value, "run-1", 5)
    value.update(has_more=False, after=0, next_after=0)
    with pytest.raises(ValueError):
        PublicRunPage.parse(value, "run-1", 0)
