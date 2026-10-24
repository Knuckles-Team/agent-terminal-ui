"""Current public run-operation consumer fixtures, not released-stack acceptance."""

import asyncio
import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from arbora.client._generated_models import REGISTRY_DIGEST, schema_for
from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable, Static

from agent_terminal_ui.client import AgentClient, ArboraOperationError
from agent_terminal_ui.commands import CommandProcessor
from agent_terminal_ui.public_run_events import (
    MAX_EVENTS,
    MAX_VIEW_BYTES,
    PublicRunPage,
    PublicRunSummary,
)
from agent_terminal_ui.tui.run_inspector import RunInspectorScreen

pytestmark = pytest.mark.spec("TUI-RUNTIME-R010.1")


def summary():
    return {
        "schema_version": "arbora-run-events-v1",
        "availability": "available",
        "run_id": "run-1",
        "task_id": "task-1",
        "status": "running",
        "current_plan": {"availability": "unavailable"},
    }


def envelope(value):
    return {
        "ok": True,
        "meta": {"registry_digest": REGISTRY_DIGEST},
        "result": {"value": value},
    }


@pytest.mark.asyncio
@pytest.mark.usefixtures("current_public_run_schema")
async def test_run_summary_uses_only_generated_operation():
    requests = []

    def reply(request):
        requests.append(request)
        assert request.url.path == "/api/v1/ops/runs.get"
        assert json.loads(request.content) == {"run_id": "run-1"}
        return httpx.Response(200, json=envelope(summary()))

    client = AgentClient(base_url="http://localhost")
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
    try:
        result = await client.get_run_summary("run-1")
        assert (result.run_id, result.task_id, result.status) == (
            "run-1",
            "task-1",
            "running",
        )
        assert len(requests) == 1
    finally:
        await client._http_client.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures("current_public_run_schema")
async def test_unknown_run_operation_has_no_legacy_fallback():
    requests = []

    def reply(request):
        requests.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "ok": False,
                "meta": {"registry_digest": REGISTRY_DIGEST},
                "error": {"code": "UNKNOWN_OP"},
            },
        )

    client = AgentClient(base_url="http://localhost")
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
    try:
        with pytest.raises(ArboraOperationError, match="UNKNOWN_OP"):
            await client.get_run_summary("run-1")
        assert requests == ["/api/v1/ops/runs.get"]
    finally:
        await client._http_client.aclose()


@pytest.mark.asyncio
async def test_run_without_id_refuses_discovery_without_repurposing_plan():
    app = MagicMock()
    app.last_run_id = None
    await CommandProcessor(app).cmd_run("")
    app.open_run_inspector.assert_not_called()
    app.open_current_plan.assert_not_called()
    assert "run ID" in app.notify.call_args.args[0]


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "legacy"},
        {"availability": "unavailable"},
        {"run_id": "other"},
        {"task_id": "other"},
        {"task_id": "bad\x1b"},
        {"status": "invented"},
        {"status": 0},
    ],
)
def test_overview_refuses_invalid_identity_and_state(change):
    raw = summary() | change
    with pytest.raises(ValueError):
        PublicRunSummary.parse(raw, "run-1", "task-1")


def test_overview_does_not_promote_unknown_fields_to_rendered_facts():
    raw = summary() | {
        "reasoning": "private",
        "cost_usd": 0,
        "harness_config": "private",
    }
    assert vars(PublicRunSummary.parse(raw, "run-1")) == {
        "run_id": "run-1",
        "task_id": "task-1",
        "status": "running",
    }


@pytest.mark.asyncio
@pytest.mark.usefixtures("current_public_run_schema")
async def test_overview_preserves_task_binding_and_rejects_invalid_ids_before_request():
    requests = []

    def reply(request):
        requests.append(request)
        assert json.loads(request.content) == {"run_id": "run-1", "task_id": "task-1"}
        return httpx.Response(200, json=envelope(summary()))

    client = AgentClient(base_url="http://localhost")
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
    try:
        assert (
            await client.get_run_summary("run-1", task_id="task-1")
        ).task_id == "task-1"
        for run, task in [
            ("", None),
            ("bad\n", None),
            ("r" * 513, None),
            ("run-1", ""),
        ]:
            with pytest.raises(ValueError):
                await client.get_run_summary(run, task_id=task)
        assert len(requests) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_old_sdk_missing_operation_refuses_before_network(monkeypatch):
    def missing(_op):
        raise KeyError("runs.get")

    monkeypatch.setattr("arbora.client._generated_models.schema_for", missing)
    client = AgentClient(base_url="http://localhost")
    client._http_client.post = AsyncMock(side_effect=AssertionError("no request"))
    try:
        with pytest.raises(ArboraOperationError, match="UNKNOWN_OP"):
            await client.get_run_summary("run-1")
        client._http_client.post.assert_not_called()
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["runs.get", "runs.events"])
async def test_untouched_installed_sdk_without_operation_refuses_before_http(operation):
    try:
        schema_for(operation)
    except KeyError:
        pass
    else:
        pytest.skip(
            "Installed SDK includes this operation; old-SDK qualification unavailable"
        )

    requests = []

    def reply(request):
        requests.append(request)
        raise AssertionError("Unsupported operations must not reach HTTP")

    client = AgentClient(base_url="http://localhost")
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
    try:
        with pytest.raises(ArboraOperationError, match="UNKNOWN_OP"):
            if operation == "runs.get":
                await client.get_run_summary("run-1")
            else:
                await client.get_public_run_events("run-1", task_id="task-1")
        assert requests == []
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.usefixtures("current_public_run_schema")
@pytest.mark.parametrize(
    "response",
    [
        {
            "ok": True,
            "meta": {"registry_digest": "old-server"},
            "result": {"value": summary()},
        },
        envelope(
            {
                "schema_version": "arbora-run-events-v1",
                "availability": "unavailable",
                "run_id": "run-1",
            }
        ),
        envelope({}),
    ],
)
async def test_old_or_unavailable_server_refuses_without_another_route(response):
    requests = []

    def reply(request):
        requests.append(request.url.path)
        return httpx.Response(200, json=response)

    client = AgentClient(base_url="http://localhost")
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
    try:
        with pytest.raises((ArboraOperationError, ValueError)):
            await client.get_run_summary("run-1")
        assert requests == ["/api/v1/ops/runs.get"]
    finally:
        await client.close()


def page():
    return json.loads(
        (Path(__file__).parents[0] / "fixtures/public_run_events.json").read_text()
    )


class InspectorApp(App):
    def __init__(self, client):
        super().__init__()
        self.agent_client = client
        self.current_session_id = "context-1"

    def compose(self) -> ComposeResult:
        yield Static("composer")

    def on_mount(self):
        self.push_screen(
            RunInspectorScreen(
                self.agent_client,
                "run-1",
                context_id=self.current_session_id,
                task_id="task-1",
                poll_interval=10,
            )
        )


def fake_client():
    client = AsyncMock(spec=AgentClient)
    client.get_run_summary.return_value = PublicRunSummary("run-1", "task-1", "running")
    client.get_public_run_events.return_value = page()
    return client


def assert_cleared(screen):
    assert screen.summary is None and screen.events == [] and screen.next_after == 0
    assert screen.query_one(DataTable).row_count == 0
    assert "unavailable" in str(
        screen.query_one("#run-inspector-summary", Static).render()
    )
    assert "unavailable" in str(
        screen.query_one("#run-inspector-payload", Static).render()
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("current_public_run_schema")
async def test_mounted_canonical_transport_overview_events_and_literal_payload():
    requests = []

    def reply(request):
        requests.append((request.url.path, json.loads(request.content)))
        if request.url.path == "/api/v1/ops/runs.get":
            return httpx.Response(200, json=envelope(summary()))
        assert request.url.path == "/api/v1/ops/runs.events"
        return httpx.Response(200, json=envelope(page()))

    client = AgentClient(base_url="http://localhost")
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
    app = InspectorApp(client)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            assert requests == [
                ("/api/v1/ops/runs.get", {"run_id": "run-1", "task_id": "task-1"}),
                (
                    "/api/v1/ops/runs.events",
                    {"run_id": "run-1", "task_id": "task-1", "after": 0, "limit": 1000},
                ),
            ]
            overview = str(screen.query_one("#run-inspector-summary", Static).render())
            assert "Task: task-1" in overview and "Status: running" in overview
            assert "context budget, cost and terminal reason: unavailable" in overview
            assert (
                screen.next_after == 5
                and screen.terminal_event_type == "graph_complete"
            )
            table = screen.query_one(DataTable)
            table.focus()
            table.move_cursor(row=1)
            await pilot.press("enter")
            assert "[bold]literal[/bold]" in str(
                screen.query_one("#run-inspector-payload", Static).render()
            )
            await pilot.press("escape")
            assert app.screen is not screen
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [ArboraOperationError("DENIED"), ValueError("invalid page")]
)
async def test_refusal_after_success_clears_all_protected_values(failure):
    client = fake_client()
    app = InspectorApp(client)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.events
        client.get_public_run_events.side_effect = failure
        screen.action_replay()
        assert_cleared(screen)
        await pilot.pause()
        assert_cleared(screen)
        assert not screen.following
        assert "unavailable" in str(
            screen.query_one("#run-inspector-status", Static).render()
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["refresh", "close", "client", "context"])
async def test_pending_and_cancel_suppressing_reads_cannot_publish_after_ownership_changes(
    action,
):
    client = fake_client()
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def read(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ArboraOperationError("DENIED")
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()
        return PublicRunSummary("run-1", "task-1", "running")

    client.get_run_summary.side_effect = read
    app = InspectorApp(client)
    async with app.run_test() as pilot:
        await started.wait()
        screen = app.screen
        if action == "refresh":
            await pilot.press("r")
            await pilot.pause()
        elif action == "close":
            await pilot.press("escape")
            assert app.screen is not screen
        elif action == "client":
            app.agent_client = fake_client()
        else:
            app.current_session_id = "other-context"
        release.set()
        await pilot.pause()
        client.get_public_run_events.assert_not_called()
        if action != "close":
            assert_cleared(screen)
        assert calls == (2 if action == "refresh" else 1)


@pytest.mark.asyncio
async def test_owner_change_clears_completed_visible_inspection():
    app = InspectorApp(fake_client())
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.events and not screen.following
        app.agent_client = fake_client()
        await pilot.press("f")
        await pilot.pause()
        assert_cleared(screen)
        app.agent_client.get_run_summary.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["client", "context"])
@pytest.mark.parametrize("action", ["row", "follow", "button"])
@pytest.mark.parametrize("terminal", [False, True])
async def test_owner_change_clears_before_protected_event_without_idle(
    owner, action, terminal
):
    client = fake_client()
    if not terminal:
        value = page()
        value.update(events=value["events"][:-1], next_after=4, terminal=False)
        client.get_public_run_events.return_value = value
    app = InspectorApp(client)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        if not terminal:
            screen.action_toggle_follow()
        assert screen.events and not screen.following
        client.get_run_summary.reset_mock()
        client.get_public_run_events.reset_mock()
        if owner == "client":
            app.agent_client = fake_client()
        else:
            app.current_session_id = "other-context"
        # Deliberately do not yield: the protected event precedes on_idle.
        if action == "row":
            table = screen.query_one(DataTable)
            screen.on_data_table_row_selected(
                DataTable.RowSelected(
                    table, cursor_row=1, row_key=table.ordered_rows[1].key
                )
            )
        elif action == "follow":
            screen.action_toggle_follow()
        else:
            screen.on_button_pressed(
                Button.Pressed(screen.query_one("#run-inspector-more", Button))
            )
        assert_cleared(screen)
        client.get_run_summary.assert_not_called()
        client.get_public_run_events.assert_not_called()
        app.agent_client.get_run_summary.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["client", "context"])
async def test_owner_captured_before_mount_refuses_changed_owner_without_request(owner):
    client = fake_client()

    class DeferredApp(App):
        def __init__(self):
            super().__init__()
            self.agent_client = client
            self.current_session_id = "context-1"

        def compose(self) -> ComposeResult:
            yield Static("composer")

        def on_mount(self):
            screen = RunInspectorScreen(
                client, "run-1", context_id=self.current_session_id
            )
            if owner == "client":
                self.agent_client = fake_client()
            else:
                self.current_session_id = "other-context"
            self.push_screen(screen)

    app = DeferredApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert_cleared(app.screen)
        assert "context changed" in str(
            app.screen.query_one("#run-inspector-status", Static).render()
        )
        assert app.screen.query_one("#run-inspector-follow", Button).disabled
        client.get_run_summary.assert_not_called()
        client.get_public_run_events.assert_not_called()
        app.agent_client.get_run_summary.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["cursor", "duplicate", "count"])
async def test_public_cursor_duplicates_and_page_bounds_refuse_without_reset_fallback(
    invalid,
):
    first = page()
    first["events"] = first["events"][:1]
    first.update(next_after=1, terminal=False, has_more=True)
    second = copy.deepcopy(first)
    second.update(after=1, next_after=2, has_more=False)
    second["events"][0]["sequence"] = 2
    if invalid == "cursor":
        second["next_after"] = 0
    elif invalid == "count":
        second["events"] *= 1001
    client = fake_client()
    client.get_public_run_events.side_effect = [first, second]
    app = InspectorApp(client)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert_cleared(screen)
        assert not screen.following
        assert [
            call.kwargs["after"] for call in client.get_public_run_events.call_args_list
        ] == [0, 1]


@pytest.mark.asyncio
async def test_retained_public_events_are_bounded_by_bytes():
    raw = page()
    template = raw["events"][1]
    raw["events"] = []
    for sequence in range(1, 30):
        event = copy.deepcopy(template)
        event.update(sequence=sequence, event_id=f"event-{sequence}")
        event["payload"]["summary"] = "x" * 8192
        raw["events"].append(event)
    raw.update(next_after=29, terminal=False, has_more=False)
    client = fake_client()
    client.get_public_run_events.return_value = raw
    app = InspectorApp(client)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        screen.action_toggle_follow()
        assert 0 < len(screen.events) <= MAX_EVENTS
        assert (
            sum(len(event.text.encode()) for event in screen.events) <= MAX_VIEW_BYTES
        )
        assert "omitted" in str(screen.query_one("#run-inspector-gap", Static).render())


@pytest.mark.asyncio
async def test_nonterminal_follow_stays_active_until_explicit_close():
    client = fake_client()
    empty = page()
    empty.update(events=[], next_after=0, has_more=False, terminal=False)
    client.get_public_run_events.return_value = empty
    app = InspectorApp(client)
    async with asyncio.timeout(3):
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            assert screen.following and screen.terminal_event_type is None
            await pilot.press("escape")
            assert app.screen is not screen
            assert not screen.following and screen.events == []


@pytest.mark.asyncio
async def test_retained_public_event_count_is_bounded_across_pages():
    app = InspectorApp(fake_client())
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        screen._clear_protected()
        first = page()
        template = first["events"][0]
        first["events"] = [
            dict(template, sequence=i, event_id=f"event-{i}") for i in range(1, 1001)
        ]
        first.update(next_after=1000, has_more=True, terminal=False)
        screen._apply_page(PublicRunPage.parse(first, "run-1", 0))
        second = dict(
            first,
            after=1000,
            next_after=1001,
            has_more=False,
            events=[dict(template, sequence=1001, event_id="event-1001")],
        )
        screen._apply_page(PublicRunPage.parse(second, "run-1", 1000))
        assert len(screen.events) == MAX_EVENTS
        assert screen.events[0].sequence == 2 and screen.next_after == 1001
        assert screen.query_one(DataTable).row_count == MAX_EVENTS
