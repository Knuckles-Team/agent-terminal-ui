"""Flat graph source-contract tests, not released or native acceptance."""

import asyncio
import copy
import importlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from arbora.client._generated_models import REGISTRY_DIGEST
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.client import AgentClient, ArboraOperationError
from agent_terminal_ui.commands import CommandProcessor
from agent_terminal_ui.execution_graph import ExecutionGraph, GRAPH_SCHEMA
from agent_terminal_ui.tui.execution_graph import ExecutionGraphScreen

pytestmark = pytest.mark.spec("TUI-RUNTIME-R010.11", "TUI-RUNTIME-R010.12")
CONTRACT = json.loads(
    (Path(__file__).parents[0] / "fixtures/execution_graph_contract.json").read_text()
)


def value():
    return copy.deepcopy(CONTRACT["value"])


def envelope(raw):
    return {
        "ok": True,
        "meta": {"registry_digest": REGISTRY_DIGEST},
        "result": {"value": raw},
    }


@pytest.fixture
def graph_schema(monkeypatch):
    """Inject only the source schema lookup, retaining real invoker and transport."""
    models = importlib.import_module("arbora.client._generated_models")
    invoker = importlib.import_module("arbora.client.invoke")
    original = models.schema_for

    def schema(operation):
        return (
            CONTRACT["schema"]
            if operation == "runs.execution_graph"
            else original(operation)
        )

    monkeypatch.setattr(models, "schema_for", schema)
    monkeypatch.setattr(invoker, "schema_for", schema)


async def client_for(reply):
    client = AgentClient(base_url="http://localhost")
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
    return client


class GraphApp(App):
    open_execution_graph = AgentApp.open_execution_graph

    def __init__(self, client):
        super().__init__()
        self.agent_client = client
        self.current_session_id = "context-one"
        self.last_run_id = "must-not-be-guessed"
        self.draft = "preserve the root draft"

    def compose(self) -> ComposeResult:
        yield Static("Root conversation")


def rendered(screen, selector):
    return str(screen.query_one(selector, Static).content)


async def settle(pilot, screen):
    for _ in range(50):
        await pilot.pause(0.01)
        if "Reading authorized" not in rendered(screen, "#execution-status"):
            return
    raise AssertionError("graph read did not finish")


@pytest.mark.asyncio
@pytest.mark.usefixtures("graph_schema")
async def test_real_command_screen_adapter_and_diamond_keyboard_navigation():
    requests = []

    def reply(request):
        requests.append(request)
        assert request.url.path == "/api/v1/ops/runs.execution_graph"
        assert json.loads(request.content) == {
            "run_id": "run-one",
            "schema_version": GRAPH_SCHEMA,
        }
        return httpx.Response(200, json=envelope(value()))

    client = await client_for(reply)
    app = GraphApp(client)
    try:
        async with app.run_test(size=(40, 24)) as pilot:
            await CommandProcessor(app).cmd_run("graph run-one")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ExecutionGraphScreen)
            await settle(pilot, screen)
            table = screen.query_one("#execution-nodes", DataTable)
            assert table.row_count == 4
            for control in (
                "execution-nodes",
                "execution-records",
                "execution-refresh",
                "execution-close",
            ):
                region = screen.query_one(f"#{control}").region
                assert region.width > 0 and region.height > 0
                assert 0 <= region.x < region.right <= 40
                assert 0 <= region.y < region.bottom <= 24
            assert screen.graph is not None
            assert len(screen.graph.edges) == 4
            assert "Lifecycle incomplete" in rendered(screen, "#execution-status")
            assert "more events: no" in rendered(screen, "#execution-status")
            await pilot.press("down", "down", "down")
            assert screen.selected_key == value()["snapshot"]["nodes"][3]["key"]
            assert "Predecessors: left, right" in rendered(screen, "#execution-edges")
            assert "left -> join" in rendered(screen, "#execution-edges")
            assert "right -> join" in rendered(screen, "#execution-edges")
            assert "Root task: work-item:" in rendered(screen, "#execution-detail")
            assert "No lifecycle event observed" in rendered(
                screen, "#execution-detail"
            )
            assert "continuation: unavailable" in rendered(screen, "#execution-detail")
            assert app.current_session_id == "context-one"
            assert app.draft == "preserve the root draft"
            await pilot.press("tab")
            assert app.focused.id == "execution-records"
            await pilot.resize_terminal(100, 40)
            assert screen.selected_key is not None
            assert screen.selected_key.endswith('"join"]')
            await pilot.press("escape")
            assert screen.graph is None and screen.selected_key is None
            assert app.screen is not screen
        assert len(requests) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("args", ["graph", "graph one two three"])
async def test_graph_requires_explicit_identity_without_guessing(args):
    app = MagicMock()
    app.last_run_id = "trace-looking-run"
    await CommandProcessor(app).cmd_run(args)
    app.open_execution_graph.assert_not_called()
    app.open_run_inspector.assert_not_called()
    assert "Usage: /run graph" in app.notify.call_args.args[0]


@pytest.mark.asyncio
async def test_graph_optional_root_is_not_a_step_or_context():
    app = MagicMock()
    await CommandProcessor(app).cmd_run("graph run-one explicit-root")
    app.open_execution_graph.assert_called_once_with("run-one", task_id="explicit-root")
    app.open_run_inspector.assert_not_called()
    app.open_current_plan.assert_not_called()


@pytest.mark.asyncio
async def test_missing_sdk_operation_refuses_before_network(monkeypatch):
    models = importlib.import_module("arbora.client._generated_models")
    original = models.schema_for

    def missing(operation):
        if operation == "runs.execution_graph":
            raise KeyError(operation)
        return original(operation)

    monkeypatch.setattr(models, "schema_for", missing)
    client = AgentClient(base_url="http://localhost")
    client._http_client.post = AsyncMock(side_effect=AssertionError("no network"))
    try:
        with pytest.raises(ArboraOperationError, match="UNKNOWN_OP"):
            await client.get_execution_graph("run-one")
        client._http_client.post.assert_not_called()
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.usefixtures("graph_schema")
async def test_explicit_root_and_invalid_input_before_request():
    requests = []
    raw = value()

    def reply(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=envelope(raw))

    client = await client_for(reply)
    try:
        graph = await client.get_execution_graph("run-one", task_id=raw["task_id"])
        assert requests == [
            {
                "run_id": "run-one",
                "task_id": raw["task_id"],
                "schema_version": GRAPH_SCHEMA,
            }
        ]
        assert graph.task_id != graph.nodes[0].task_id
        for run, task in [
            ("", None),
            ("r" * 513, None),
            ("run-one", ""),
            ("run-one", "t" * 513),
        ]:
            with pytest.raises(ValueError):
                await client.get_execution_graph(run, task_id=task)
        assert len(requests) == 1
    finally:
        await client.close()


@pytest.mark.parametrize(
    "field,bad",
    [
        ("schema_version", "legacy"),
        ("availability", "unavailable"),
        ("run_id", "other"),
        ("task_id", "other"),
        ("snapshot", None),
    ],
)
def test_graph_identity_is_exact(field, bad):
    raw = value()
    root = raw["task_id"]
    raw[field] = bad
    with pytest.raises(ValueError):
        ExecutionGraph.parse(raw, "run-one", root)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("topology_completeness", "partial"),
        ("lifecycle_completeness", "complete"),
        ("lifecycle_reason", "terminal"),
        ("covered_after", True),
        ("covered_after", 1001),
        ("covered_after", -1),
        ("has_more", 1),
        ("can_read_transcript", True),
        ("can_message_active", True),
        ("can_continue_completed", True),
        ("supports_spawned_children", True),
        ("nodes", []),
        ("nodes", [None] * 65),
        ("edges", [None] * 2017),
        ("plan_digest", "p" * 513),
    ],
)
def test_graph_refuses_unsupported_or_unbounded_projection(field, bad):
    raw = value()
    raw["snapshot"][field] = bad
    with pytest.raises(ValueError):
        ExecutionGraph.parse(raw, "run-one")


@pytest.mark.parametrize(
    "case",
    [
        "cross-run",
        "duplicate-node",
        "dangling",
        "duplicate-edge",
        "cycle",
        "child",
        "missing-evidence",
        "false-evidence",
        "future-evidence",
        "bool-evidence",
        "oversize",
    ],
)
def test_graph_refuses_false_topology_and_lifecycle(case):
    raw = value()
    nodes, edges = raw["snapshot"]["nodes"], raw["snapshot"]["edges"]
    if case == "cross-run":
        nodes[0]["key"] = json.dumps(
            ["other", "plan_step", "first"], separators=(",", ":")
        )
    elif case == "duplicate-node":
        nodes.append(copy.deepcopy(nodes[0]))
    elif case == "dangling":
        edges[0]["source"] = "missing"
    elif case == "duplicate-edge":
        edges.append(copy.deepcopy(edges[0]))
    elif case == "cycle":
        edges.append(
            {
                "kind": "depends_on",
                "source": nodes[-1]["key"],
                "target": nodes[0]["key"],
            }
        )
    elif case == "child":
        edges[0]["kind"] = "spawned_child"
    elif case == "missing-evidence":
        nodes[0]["evidence"] = None
    elif case == "false-evidence":
        nodes[1]["evidence"] = nodes[0]["evidence"]
    elif case == "future-evidence":
        nodes[0]["evidence"]["sequence"] = 3
    elif case == "bool-evidence":
        nodes[0]["evidence"]["sequence"] = True
    elif case == "oversize":
        raw["private"] = "x" * 1_048_576
    with pytest.raises(ValueError):
        ExecutionGraph.parse(raw, "run-one")


@pytest.mark.asyncio
@pytest.mark.usefixtures("graph_schema")
@pytest.mark.parametrize(
    "failure", ["denial", "unknown-op", "digest", "malformed", "wrong-root"]
)
async def test_refresh_clears_before_read_and_fails_closed(failure):
    requests, waiting, release = [], asyncio.Event(), asyncio.Event()
    raw = value()

    async def reply(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=envelope(raw))
        assert json.loads(request.content)["task_id"] == raw["task_id"]
        waiting.set()
        await release.wait()
        result = envelope(value())
        if failure in {"denial", "unknown-op"}:
            result = {
                "ok": False,
                "meta": {"registry_digest": REGISTRY_DIGEST},
                "error": {
                    "code": "FORBIDDEN" if failure == "denial" else "UNKNOWN_OP",
                    "message": "private-error",
                },
            }
        elif failure == "digest":
            result["meta"]["registry_digest"] = "different"
        elif failure == "malformed":
            result["result"]["value"] = {"private": "secret"}
        else:
            result["result"]["value"]["task_id"] = "other-root"
        return httpx.Response(200, json=result)

    client = await client_for(reply)
    app = GraphApp(client)
    try:
        async with app.run_test() as pilot:
            app.open_execution_graph("run-one")
            await pilot.pause()
            screen = app.screen
            await settle(pilot, screen)
            assert screen.graph is not None
            await pilot.press("r")
            await asyncio.wait_for(waiting.wait(), 2)
            assert screen.graph is None
            assert screen.query_one("#execution-nodes", DataTable).row_count == 0
            assert "Root task" not in rendered(screen, "#execution-detail")
            release.set()
            await settle(pilot, screen)
            assert "Graph unavailable" in rendered(screen, "#execution-status")
            assert screen.graph is None
            assert "private-error" not in rendered(screen, "#execution-status")
            assert all(
                r.url.path == "/api/v1/ops/runs.execution_graph" for r in requests
            )
    finally:
        release.set()
        await client.close()


@pytest.mark.asyncio
@pytest.mark.usefixtures("graph_schema")
@pytest.mark.parametrize("drift", ["context", "client", "endpoint", "credential"])
async def test_owner_change_clears_and_never_reuses_the_graph(drift):
    client = await client_for(
        lambda request: httpx.Response(200, json=envelope(value()))
    )
    app = GraphApp(client)
    try:
        async with app.run_test() as pilot:
            app.open_execution_graph("run-one")
            await pilot.pause()
            screen = app.screen
            await settle(pilot, screen)
            if drift == "context":
                app.current_session_id = "context-two"
            elif drift == "client":
                app.agent_client = object()
            elif drift == "endpoint":
                client.base_url = "http://127.0.0.1"
            else:
                client._http_client.headers["Authorization"] = (
                    "Bearer changed-test-token"
                )
            await pilot.pause()
            assert screen.graph is None
            assert screen.selected_key is None
            assert "Close and reopen" in rendered(screen, "#execution-status")
            assert "work-item" not in rendered(screen, "#execution-detail")
            await pilot.press("r")
            assert screen.graph is None
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.usefixtures("graph_schema")
async def test_late_result_after_close_cannot_repopulate():
    started, release = asyncio.Event(), asyncio.Event()

    async def reply(request):
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()
        return httpx.Response(200, json=envelope(value()))

    client = await client_for(reply)
    app = GraphApp(client)
    try:
        async with app.run_test() as pilot:
            app.open_execution_graph("run-one")
            await pilot.pause()
            screen = app.screen
            await asyncio.wait_for(started.wait(), 2)
            await pilot.press("escape")
            release.set()
            await pilot.pause()
            assert screen.graph is None and screen.selected_key is None
            assert app.screen is not screen
    finally:
        release.set()
        await client.close()


@pytest.mark.asyncio
@pytest.mark.usefixtures("graph_schema")
async def test_literal_untrusted_identity_and_private_fields_not_rendered():
    raw = value()
    old = raw["snapshot"]["nodes"][0]["key"]
    hostile = "[bold]step[/bold]\x1b\u202eevil"
    node = raw["snapshot"]["nodes"][0]
    node["task_id"] = hostile
    node["key"] = json.dumps(["run-one", "plan_step", hostile], separators=(",", ":"))
    node["private_reasoning"] = "DO NOT DISPLAY"
    raw["snapshot"]["transcript"] = "DO NOT DISPLAY"
    raw["snapshot"]["has_more"] = True
    for edge in raw["snapshot"]["edges"]:
        if edge["source"] == old:
            edge["source"] = node["key"]
    client = await client_for(lambda request: httpx.Response(200, json=envelope(raw)))
    try:
        async with GraphApp(client).run_test() as pilot:
            pilot.app.open_execution_graph("run-one")
            await pilot.pause()
            screen = pilot.app.screen
            await settle(pilot, screen)
            text = rendered(screen, "#execution-detail") + rendered(
                screen, "#execution-edges"
            )
            assert "[bold]step[/bold]evil" in text
            assert "\x1b" not in text and "\u202e" not in text
            assert "DO NOT DISPLAY" not in text
            assert screen.graph.nodes[0].task_id == hostile
            assert "more events: yes" in rendered(screen, "#execution-status")
            screen._select_node("missing")
            assert screen.selected_key is None
            assert rendered(screen, "#execution-detail") == "Details unavailable."
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.usefixtures("graph_schema")
@pytest.mark.parametrize("change", ["refresh", "context"])
async def test_late_response_cannot_restore_prior_selection_or_owner(change):
    started, release = asyncio.Event(), asyncio.Event()
    requests = []

    async def reply(request):
        requests.append(request)
        count = len(requests)
        if count == 2:
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
        raw = value()
        raw["snapshot"]["plan_digest"] = (
            "stale-second" if count == 2 else f"current-{count}"
        )
        return httpx.Response(200, json=envelope(raw))

    client = await client_for(reply)
    app = GraphApp(client)
    try:
        async with app.run_test() as pilot:
            app.open_execution_graph("run-one")
            await pilot.pause()
            screen = app.screen
            await settle(pilot, screen)
            await pilot.press("down", "down")
            assert screen.selected_key.endswith('"right"]')
            await pilot.press("r")
            await asyncio.wait_for(started.wait(), 2)
            assert screen.graph is None and screen.selected_key is None
            if change == "refresh":
                await pilot.press("r")
                await settle(pilot, screen)
                assert screen.graph is not None
                assert screen.graph.plan_digest == "current-3"
            else:
                app.current_session_id = "context-new"
                await pilot.pause()
                assert screen.graph is None
            release.set()
            await pilot.pause()
            assert "stale-second" not in rendered(screen, "#execution-detail")
            if change == "refresh":
                assert screen.graph is not None
                assert screen.graph.plan_digest == "current-3"
                assert screen.selected_key is not None
                assert screen.selected_key.endswith('"first"]')
            else:
                assert screen.graph is None
                assert "Close and reopen" in rendered(screen, "#execution-status")
    finally:
        release.set()
        await client.close()


@pytest.mark.asyncio
@pytest.mark.usefixtures("graph_schema")
@pytest.mark.parametrize("change", ["context", "client", "credential", "close"])
async def test_dispatch_gap_rechecks_owner_before_any_transport(change, monkeypatch):
    pending, requests = [], []

    def hold_worker(_screen, work, *args, **kwargs):
        pending.append(work)
        return MagicMock()

    def reply(request):
        requests.append(request)
        return httpx.Response(200, json=envelope(value()))

    monkeypatch.setattr(ExecutionGraphScreen, "run_worker", hold_worker)
    client = await client_for(reply)
    app = GraphApp(client)
    try:
        async with app.run_test() as pilot:
            app.open_execution_graph("run-one")
            await pilot.pause()
            screen = app.screen
            assert len(pending) == 1 and not requests
            if change == "context":
                app.current_session_id = "context-new"
            elif change == "client":
                app.agent_client = object()
            elif change == "credential":
                client._http_client.headers["Authorization"] = "Bearer new-test-token"
            else:
                screen.action_close()
            await pending.pop()
            assert requests == []
            assert screen.graph is None
    finally:
        for coroutine in pending:
            coroutine.close()
        await client.close()


@pytest.mark.parametrize("duplicate", ["event_id", "sequence"])
def test_distinct_steps_cannot_share_last_lifecycle_evidence(duplicate):
    raw = value()
    nodes = raw["snapshot"]["nodes"]
    nodes[1]["status"] = "running"
    nodes[1]["evidence"] = {"event_id": "different-event", "sequence": 1}
    nodes[1]["evidence"][duplicate] = nodes[0]["evidence"][duplicate]
    with pytest.raises(ValueError, match="duplicate lifecycle evidence"):
        ExecutionGraph.parse(raw, "run-one")


@pytest.mark.asyncio
@pytest.mark.usefixtures("graph_schema")
async def test_actual_producer_unicode_keys_survive_transport_and_selection():
    raw = copy.deepcopy(CONTRACT["unicode_value"])
    requests = []

    def reply(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=envelope(raw))

    client = await client_for(reply)
    try:
        async with GraphApp(client).run_test(size=(40, 24)) as pilot:
            pilot.app.open_execution_graph(raw["run_id"], task_id=raw["task_id"])
            await pilot.pause()
            screen = pilot.app.screen
            await settle(pilot, screen)
            assert screen.graph is not None
            assert screen.graph.run_id == "运行-α"
            assert screen.graph.task_id == "根-β"
            assert screen.graph.nodes[0].task_id == "準備-ñ"
            await pilot.press("down")
            assert screen.selected_key == raw["snapshot"]["nodes"][1]["key"]
            assert screen.selected_key is not None
            assert "\\ud83d\\ude42" in screen.selected_key
            assert "結合-🙂" in rendered(screen, "#execution-detail")
            assert "準備-ñ -> 結合-🙂" in rendered(screen, "#execution-edges")
            assert requests == [
                {"run_id": "运行-α", "task_id": "根-β", "schema_version": GRAPH_SCHEMA}
            ]
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.usefixtures("graph_schema")
async def test_actual_producer_maximum_unicode_ids_use_codepoint_bounds():
    raw = copy.deepcopy(CONTRACT["max_unicode_value"])
    requests = []

    def reply(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=envelope(raw))

    client = await client_for(reply)
    try:
        graph = await client.get_execution_graph(raw["run_id"], task_id=raw["task_id"])
        assert graph.run_id == "🙂" * 512
        assert graph.nodes[0].task_id == "🙂" * 512
        assert len(graph.nodes[0].key) == 12307
        assert (
            CONTRACT["schema"]["result"]["$defs"]["ExecutionStep"]["properties"]["key"][
                "maxLength"
            ]
            == 16384
        )
        assert requests[0]["run_id"] == graph.run_id
        with pytest.raises(ValueError):
            await client.get_execution_graph("🙂" * 513, task_id="root")
        assert len(requests) == 1
    finally:
        await client.close()
