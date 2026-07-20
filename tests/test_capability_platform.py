"""Focused tests for the shared capability and canonical run contracts."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Input, Static

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.capabilities import (
    TERMINAL_RUN_EVENT_TYPES,
    CapabilityCatalog,
    CapabilityDescriptor,
    CapabilityInvocation,
    CapabilityPreflight,
    RunCatalog,
    RunEventPage,
    RunSummary,
    SchemaInputError,
    is_terminal_run_event_type,
    parse_schema_input,
    schema_fields,
)
from agent_terminal_ui.capability_provider import CapabilityCommandProvider
from agent_terminal_ui.client import AgentClient
from agent_terminal_ui.commands import CommandProcessor
from agent_terminal_ui.tui.capability_palette import (
    CapabilityConfirmationScreen,
    CapabilityPaletteScreen,
)
from agent_terminal_ui.tui.run_inspector import RunBrowserScreen, RunInspectorScreen
from agent_terminal_ui.widgets.capability_sidebar import CapabilitySidebar


def _descriptor_payload(*, mutates: bool = False) -> dict[str, Any]:
    return {
        "id": "demo_tool",
        "title": "Demo tool",
        "one_line": "Inspect or update a demo value.",
        "intent_verbs": ["inspect"],
        "availability": {
            "status": "available",
            "reasons": [],
            "missing_preconditions": [],
        },
        "typed_io": {
            "legacy_rest_route": "/wrong/aggregate-route",
            "tags": ["graph", "query"],
        },
        "execution": {
            "governed_invoke_route": "/api/capabilities/demo_tool/invoke",
            "normative_frontend_contract": "governed_invoke",
            "eventual_result_event": "tool_result",
        },
        "render": {"renderer": "table"},
        "actions": [
            {
                "id": "inspect",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "const": "inspect",
                            "default": "inspect",
                        },
                        "value": {
                            "type": "integer",
                            "description": "Value to inspect.",
                        },
                        "verbose": {"type": "boolean", "default": False},
                    },
                    "required": ["action", "value"],
                },
                "typed_io": {
                    "legacy_rest_route": "/graph/demo",
                    "legacy_request_encoding": "action_in_body",
                    "frontend_executable": False,
                },
                "side_effects": {
                    "mutates": mutates,
                    "idempotent": not mutates,
                    "audited": True,
                },
                "policy": {
                    "approval_class": "confirm" if mutates else "auto",
                    "authoritative_at_execution": True,
                },
            }
        ],
    }


def _catalog_payload(*, mutates: bool = False) -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "catalog_version": "catalog-1",
        "runtime": {"status": "ready", "backend_ready": True},
        "count": 1,
        "action_count": 1,
        "capabilities": [_descriptor_payload(mutates=mutates)],
    }


def _preflight_payload(*, mutates: bool = False) -> dict[str, Any]:
    return {
        "capability_id": "demo_tool",
        "action": "inspect",
        "valid": True,
        "validation_issues": [],
        "availability": {
            "status": "available",
            "reasons": [],
            "missing_preconditions": [],
        },
        "policy": {
            "decision": "allow",
            "tier": "confirm" if mutates else "auto",
            "reason": "test policy",
            "approval_required": False,
            "authoritative": False,
            "identity_evaluated": False,
            "must_recheck_at_execution": True,
        },
        "eligible": True,
        "executable_now": True,
        "side_effects": {"mutates": mutates, "audited": True},
    }


def _run_summary_payload() -> dict[str, Any]:
    return {
        "run_id": "run-1",
        "session_id": "session-1",
        "trace_id": "trace-1",
        "status": "completed",
        "first_sequence": 1,
        "last_sequence": 2,
        "event_count": 2,
        "truncated": False,
        "first_timestamp": "2026-07-13T00:00:00Z",
        "last_timestamp": "2026-07-13T00:00:01Z",
        "last_event_type": "run_completed",
    }


def _run_page_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": "run-1",
        "after": 0,
        "next_after": 2,
        "has_more": False,
        "retained_from": 1,
        "events": [
            {
                "schema_version": "1.0",
                "event_id": "run-1:1",
                "sequence": 1,
                "timestamp": "2026-07-13T00:00:00Z",
                "type": "run_started",
                "run_id": "run-1",
                "session_id": "session-1",
                "source": "agent-utilities",
                "payload": {"prompt": "hello"},
            },
            {
                "schema_version": "1.0",
                "event_id": "run-1:2",
                "sequence": 2,
                "timestamp": "2026-07-13T00:00:01Z",
                "type": "run_completed",
                "run_id": "run-1",
                "session_id": "session-1",
                "source": "agent-utilities",
                "payload": {"status": "success"},
            },
        ],
    }


def _run_event(sequence: int, event_type: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "event_id": f"run-1:{sequence}",
        "sequence": sequence,
        "timestamp": f"2026-07-13T00:00:{sequence:02d}Z",
        "type": event_type,
        "run_id": "run-1",
        "session_id": "session-1",
        "source": "agent-utilities",
        "payload": {"status": event_type},
    }


def _run_page(
    after: int,
    *events: dict[str, Any],
    has_more: bool = False,
    retained_from: int = 1,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": "run-1",
        "after": after,
        "next_after": events[-1]["sequence"] if events else after,
        "has_more": has_more,
        "retained_from": retained_from,
        "events": list(events),
    }


def test_models_parse_catalog_and_schema_values() -> None:
    catalog = CapabilityCatalog.from_payload(_catalog_payload())
    descriptor = catalog.find("demo_tool")

    assert catalog.schema_version == "2.0"
    assert descriptor is not None
    assert descriptor.rest_route == "/wrong/aggregate-route"
    assert descriptor.governed_invoke_route == "/api/capabilities/demo_tool/invoke"
    assert "inspect" in descriptor.search_text
    assert descriptor.availability.is_available

    action = descriptor.action("inspect")
    assert action is not None
    assert action.rest_route == "/graph/demo"
    assert action.request_encoding == "action_in_body"
    assert not action.frontend_executable
    fields = {field.name: field for field in schema_fields(action.input_schema)}
    assert parse_schema_input(fields["action"], "ignored") == (True, "inspect")
    assert parse_schema_input(fields["value"], "7") == (True, 7)
    assert parse_schema_input(fields["verbose"], "true") == (True, True)
    with pytest.raises(SchemaInputError, match="use true or false"):
        parse_schema_input(fields["verbose"], "yes")

    cold_payload = _descriptor_payload()
    cold_payload["availability"]["readiness"] = "cold"
    cold = CapabilityDescriptor.from_payload(cold_payload)
    assert cold.availability.is_available
    assert cold.availability.display_status == "available (cold)"

    queued_payload = _preflight_payload(mutates=True)
    queued_payload["policy"]["decision"] = "queue_approval"
    queued_payload["policy"]["approval_required"] = True
    queued_payload["executable_now"] = False
    queued = CapabilityPreflight.from_payload(queued_payload)
    assert queued.requires_confirmation
    assert not queued.executable_now


def test_run_terminal_contract_excludes_graph_and_output_progress() -> None:
    assert TERMINAL_RUN_EVENT_TYPES == {
        "run_completed",
        "run_failed",
        "run_interrupted",
        "run_cancelled",
        "error",
    }
    for event_type in TERMINAL_RUN_EVENT_TYPES:
        assert is_terminal_run_event_type(event_type)
    for progress_type in (
        "graph_complete",
        "final_output",
        "tool_result",
        "node_complete",
    ):
        assert not is_terminal_run_event_type(progress_type)


def test_run_event_page_reports_bounded_replay_reset() -> None:
    page = RunEventPage.from_payload(
        _run_page(2, _run_event(5, "graph_complete"), retained_from=5)
    )

    assert page.retained_from == 5
    assert not page.events[0].is_terminal
    assert page.replay_gap is not None
    assert page.replay_gap.missing_from == 3
    assert page.replay_gap.missing_through == 4
    assert "sequences 3-4" in page.replay_gap.message


def test_capability_coverage_ledger_uses_supported_contract() -> None:
    path = Path(__file__).parents[1] / "docs" / "capability-coverage.json"
    ledger = json.loads(path.read_text(encoding="utf-8"))
    allowed = {"native", "generated", "chat_only", "hidden", "unavailable"}

    assert ledger["schema_version"] == "1.0"
    assert ledger["surface"] == "agent-terminal-ui"
    assert ledger["default_support"] == "generated"
    for override in ledger["overrides"].values():
        assert override["support"] in allowed
        assert override.get("entrypoint") or override.get("reason")


@pytest.mark.asyncio
async def test_client_consumes_live_capability_and_run_contracts() -> None:
    requests: list[tuple[str, str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        requests.append((request.method, request.url.path, body))
        path = request.url.path
        if path == "/api/capabilities":
            assert request.url.params["include_actions"] == "true"
            return httpx.Response(
                200,
                json={"status_code": 200, "data": _catalog_payload()},
            )
        if path == "/api/capabilities/demo_tool":
            return httpx.Response(200, json=_descriptor_payload())
        if path == "/api/capabilities/demo_tool/preflight":
            assert set(body) == {"action", "inputs", "target"}
            assert body["action"] == "inspect"
            assert body["inputs"]["value"] == 7
            return httpx.Response(200, json=_preflight_payload())
        if path == "/api/capabilities/demo_tool/invoke":
            assert body == {
                "action": "inspect",
                "inputs": {"action": "inspect", "value": 7},
                "session_id": "session-stable-1",
            }
            return httpx.Response(
                202,
                json={
                    "status": "running",
                    "run_id": "run-1",
                    "session_id": "session-stable-1",
                    "result": {},
                },
            )
        if path == "/api/capabilities/graph_mine/invoke":
            expected_inputs = {
                "action": "cluster",
                "params_json": '{"features":[[1.0,2.0]]}',
                "graph": "tenant-a",
            }
            if body.get("approval_id"):
                assert body == {
                    "action": "cluster",
                    "inputs": expected_inputs,
                    "approval_id": "approval-1",
                    "run_id": "run-pending-1",
                    "session_id": "session-stable-1",
                }
                return httpx.Response(
                    202,
                    json={
                        "status": "running",
                        "run_id": "run-pending-1",
                        "session_id": "session-stable-1",
                        "result": {},
                    },
                )
            assert body == {
                "action": "cluster",
                "inputs": expected_inputs,
                "session_id": "session-stable-1",
            }
            return httpx.Response(
                202,
                json={
                    "status": "approval_required",
                    "approval_id": "approval-1",
                    "run_id": "run-pending-1",
                    "session_id": "session-stable-1",
                },
            )
        if path == "/api/runs/run-1":
            return httpx.Response(200, json=_run_summary_payload())
        if path == "/api/runs":
            assert request.url.params["status"] == "completed"
            return httpx.Response(
                200,
                json={
                    "schema_version": "1.0",
                    "count": 1,
                    "runs": [_run_summary_payload()],
                },
            )
        if path == "/api/runs/run-1/events":
            assert request.url.params["after"] == "0"
            return httpx.Response(200, json=_run_page_payload())
        if path == "/api/events/schema":
            return httpx.Response(
                200, json={"schema_version": "1.0", "schema": {"type": "object"}}
            )
        return httpx.Response(404, json={"detail": "not found"})

    client = AgentClient("http://gateway.test")
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        catalog = await client.list_capabilities(query="demo")
        descriptor = await client.get_capability("demo_tool")
        preflight = await client.preflight_capability(
            "demo_tool", action="inspect", inputs={"action": "inspect", "value": 7}
        )
        action = descriptor.action("inspect")
        assert action is not None
        invocation = await client.invoke_capability(
            "demo_tool",
            {"action": "inspect", "value": 7},
            action=action.id,
            session_id="session-stable-1",
        )
        path_descriptor = CapabilityDescriptor.from_payload(
            {
                "id": "graph_mine",
                "typed_io": {"legacy_rest_route": "/wrong/first-action"},
                "execution": {
                    "governed_invoke_route": "/api/capabilities/graph_mine/invoke"
                },
                "actions": [
                    {
                        "id": "cluster",
                        "typed_io": {
                            "legacy_rest_route": "/mining/cluster",
                            "legacy_request_encoding": "action_in_path",
                            "frontend_executable": False,
                            "params_field": "params_json",
                        },
                    }
                ],
            }
        )
        path_action = path_descriptor.action("cluster")
        assert path_action is not None
        path_inputs = {
            "action": "cluster",
            "params_json": '{"features":[[1.0,2.0]]}',
            "graph": "tenant-a",
        }
        pending = await client.invoke_capability(
            "graph_mine",
            path_inputs,
            action=path_action.id,
            session_id="session-stable-1",
        )
        resumed = await client.invoke_capability(
            "graph_mine",
            path_inputs,
            action=path_action.id,
            approval_id=pending.approval_id,
            run_id=pending.run_id,
            session_id=pending.session_id,
        )
        runs = await client.list_runs(status="completed")
        summary = await client.get_run_summary("run-1")
        page = await client.get_run_events("run-1")
        schema = await client.get_event_schema()
    finally:
        await client.close()

    assert catalog.find("demo_tool") is not None
    assert preflight.executable_now
    assert invocation.run_id == "run-1"
    assert invocation.accepted
    assert not invocation.approval_required
    assert pending.approval_required
    assert pending.http_status == 202
    assert pending.approval_id == "approval-1"
    assert pending.run_id == resumed.run_id == "run-pending-1"
    assert pending.session_id == resumed.session_id == "session-stable-1"
    assert resumed.accepted
    assert resumed.succeeded
    assert runs.runs[0].status == "completed"
    assert summary.event_count == 2
    assert [event.sequence for event in page.events] == [1, 2]
    assert schema["schema_version"] == "1.0"
    assert (
        "POST",
        "/api/capabilities/demo_tool/invoke",
        {
            "action": "inspect",
            "inputs": {"action": "inspect", "value": 7},
            "session_id": "session-stable-1",
        },
    ) in requests
    assert not any(
        path in {"/api/graph/demo", "/api/mining/cluster"} for _, path, _ in requests
    )


def test_normalized_stream_event_preserves_canonical_run_identity() -> None:
    normalized = AgentClient._normalize_event(
        {
            "type": "text-delta",
            "delta": "hi",
            "_event": {"run_id": "run-1", "sequence": 2},
        },
        "session-1",
    )

    assert normalized["type"] == "text_delta"
    assert normalized["run_id"] == "run-1"
    assert normalized["_event"]["sequence"] == 2

    started = AgentClient._normalize_event(
        {
            "type": "run_started",
            "run_id": "run-execution-2",
            "session_id": "session-stable-1",
        },
        "session-stable-1",
    )
    assert started["session_id"] == "session-stable-1"
    assert started["run_id"] == "run-execution-2"
    assert started["session_id"] != started["run_id"]


@pytest.mark.asyncio
async def test_capability_and_run_slash_commands_open_live_screens() -> None:
    app = SimpleNamespace(
        open_capability_palette=lambda **kwargs: opened.append(("capability", kwargs)),
        open_run_inspector=lambda run_id: opened.append(("run", run_id)),
        last_run_id="run-latest",
        notify=lambda *args, **kwargs: None,
    )
    opened: list[tuple[str, Any]] = []
    processor = CommandProcessor(app)

    await processor.cmd_capabilities("graph")
    await processor.commands["capability"]("demo_tool")
    await processor.cmd_run("")

    assert opened == [
        ("capability", {"initial_query": "graph"}),
        ("capability", {"initial_query": "demo_tool"}),
        ("run", "run-latest"),
    ]
    assert CapabilityCommandProvider in AgentApp.COMMANDS


class _FakeCapabilityClient:
    def __init__(
        self, *, mutates: bool = False, approval_required: bool = False
    ) -> None:
        self.mutates = mutates
        self.approval_required = approval_required
        self.current_session_id = "session-stable-1"
        self.preflight_calls: list[dict[str, Any]] = []
        self.invocation_calls: list[dict[str, Any]] = []
        self.invocation_options: list[dict[str, Any]] = []
        self.approval_calls: list[tuple[str, str]] = []

    async def list_capabilities(self, **_kwargs: Any) -> CapabilityCatalog:
        return CapabilityCatalog.from_payload(_catalog_payload(mutates=self.mutates))

    async def get_capability(self, _capability_id: str) -> CapabilityDescriptor:
        return CapabilityDescriptor.from_payload(
            _descriptor_payload(mutates=self.mutates)
        )

    async def preflight_capability(
        self, _capability_id: str, **kwargs: Any
    ) -> CapabilityPreflight:
        self.preflight_calls.append(kwargs)
        return CapabilityPreflight.from_payload(
            _preflight_payload(mutates=self.mutates)
        )

    async def invoke_capability(
        self, _capability_id: str, inputs: dict[str, Any], **kwargs: Any
    ) -> CapabilityInvocation:
        self.invocation_calls.append(copy.deepcopy(inputs))
        self.invocation_options.append(dict(kwargs))
        if self.approval_required and not kwargs.get("approval_id"):
            return CapabilityInvocation(
                capability_id="demo_tool",
                result={
                    "status": "approval_required",
                    "approval_id": "approval-1",
                    "run_id": "run-pending-1",
                    "session_id": "session-stable-1",
                },
                run_id="run-pending-1",
                session_id="session-stable-1",
                approval_id="approval-1",
                status="approval_required",
                http_status=202,
            )
        return CapabilityInvocation(
            capability_id="demo_tool",
            result={"status": "running", "run_id": "run-1"},
            run_id=str(kwargs.get("run_id") or "run-1"),
            session_id=str(kwargs.get("session_id") or "session-stable-1"),
            status="running",
            http_status=202,
        )

    async def grant_fleet_approval(
        self, approval_id: str, decision: str
    ) -> dict[str, Any]:
        self.approval_calls.append((approval_id, decision))
        return {
            "status": "success",
            "result": {"approval_id": approval_id, "decision": decision},
        }

    async def get_run_summary(self, _run_id: str) -> RunSummary:
        return RunSummary.from_payload(_run_summary_payload())

    async def list_runs(self, **_kwargs: Any) -> RunCatalog:
        return RunCatalog.from_payload(
            {
                "schema_version": "1.0",
                "count": 1,
                "runs": [_run_summary_payload()],
            }
        )

    async def get_run_events(self, _run_id: str, **_kwargs: Any) -> RunEventPage:
        return RunEventPage.from_payload(_run_page_payload())


class _PaletteHarness(App[None]):
    def __init__(self, client: _FakeCapabilityClient) -> None:
        super().__init__()
        self.agent_client = client
        self.current_session_id: str | None = "session-stable-1"
        self.observed_run_id: str | None = None
        self.observed_session_id: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("harness")

    def on_mount(self) -> None:
        self.push_screen(CapabilityPaletteScreen(self.agent_client))

    def remember_run_id(self, run_id: str) -> None:
        self.observed_run_id = run_id

    def remember_session_id(self, session_id: str) -> None:
        self.current_session_id = session_id
        self.observed_session_id = session_id


@pytest.mark.asyncio
async def test_palette_generates_form_preflights_and_invokes_read_only_action() -> None:
    client = _FakeCapabilityClient()
    app = _PaletteHarness(client)

    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        assert isinstance(app.screen, CapabilityPaletteScreen)
        app.screen.query_one("#capability-field-1", Input).value = "7"
        await pilot.click("#capability-invoke-button")
        await pilot.pause(0.2)

        assert client.preflight_calls[-1]["inputs"]["value"] == 7
        assert client.invocation_calls[-1]["value"] == 7
        assert client.invocation_options[-1]["action"] == "inspect"
        assert client.invocation_options[-1]["session_id"] == "session-stable-1"
        assert app.observed_run_id == "run-1"
        assert app.observed_session_id == "session-stable-1"
        assert not app.screen.query_one("#capability-inspect-button").disabled


@pytest.mark.asyncio
async def test_palette_requires_confirmation_for_side_effects() -> None:
    client = _FakeCapabilityClient(mutates=True)
    app = _PaletteHarness(client)

    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        palette = app.screen
        assert isinstance(palette, CapabilityPaletteScreen)
        palette.query_one("#capability-field-1", Input).value = "9"
        await pilot.click("#capability-invoke-button")
        await pilot.pause(0.1)

        assert isinstance(app.screen, CapabilityConfirmationScreen)
        assert not client.invocation_calls
        await pilot.click("#capability-confirm-accept")
        await pilot.pause(0.2)

        assert client.invocation_calls[-1]["value"] == 9


@pytest.mark.asyncio
async def test_palette_resumes_exact_server_bound_request_after_approval() -> None:
    client = _FakeCapabilityClient(mutates=True, approval_required=True)
    app = _PaletteHarness(client)

    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        palette = app.screen
        assert isinstance(palette, CapabilityPaletteScreen)
        palette.query_one("#capability-field-1", Input).value = "9"
        await pilot.click("#capability-invoke-button")
        await pilot.pause(0.1)
        assert isinstance(app.screen, CapabilityConfirmationScreen)
        await pilot.click("#capability-confirm-accept")
        await pilot.pause(0.2)

        palette = app.screen
        assert isinstance(palette, CapabilityPaletteScreen)
        assert not palette.query_one("#capability-approve-button").disabled
        assert client.invocation_calls == [
            {"action": "inspect", "value": 9, "verbose": False}
        ]

        # Editing the visible form cannot alter the frozen approval request.
        palette.query_one("#capability-field-1", Input).value = "999"
        await pilot.click("#capability-approve-button")
        await pilot.pause(0.2)

        assert client.approval_calls == [("approval-1", "approved")]
        assert client.invocation_calls[1] == client.invocation_calls[0]
        assert client.invocation_options[1]["approval_id"] == "approval-1"
        assert client.invocation_options[1]["run_id"] == "run-pending-1"
        assert client.invocation_options[1]["session_id"] == "session-stable-1"
        assert app.observed_run_id == "run-pending-1"


class _SidebarHarness(App[None]):
    def __init__(self, client: _FakeCapabilityClient) -> None:
        super().__init__()
        self.agent_client = client

    def compose(self) -> ComposeResult:
        yield CapabilitySidebar()


@pytest.mark.asyncio
async def test_sidebar_searches_live_catalog() -> None:
    app = _SidebarHarness(_FakeCapabilityClient())
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        sidebar = app.query_one(CapabilitySidebar)
        assert [capability.id for capability in sidebar.filtered] == ["demo_tool"]
        app.query_one("#capability-sidebar-search", Input).value = "no match"
        await pilot.pause()
        assert sidebar.filtered == []


class _FollowClient:
    def __init__(self, *pages: dict[str, Any]) -> None:
        self.pages = list(pages)
        self.requested_after: list[int] = []

    async def get_run_summary(self, _run_id: str) -> RunSummary:
        payload = _run_summary_payload()
        payload.update(status="running", last_event_type="graph_complete")
        return RunSummary.from_payload(payload)

    async def get_run_events(
        self, _run_id: str, *, after: int, **_kwargs: Any
    ) -> RunEventPage:
        self.requested_after.append(after)
        payload = self.pages.pop(0)
        assert payload["after"] == after
        return RunEventPage.from_payload(payload)


class _RunHarness(App[None]):
    def __init__(self, client: Any, *, poll_interval: float = 0.01) -> None:
        super().__init__()
        self.agent_client = client
        self.poll_interval = poll_interval

    def compose(self) -> ComposeResult:
        yield Static("harness")

    def on_mount(self) -> None:
        self.push_screen(
            RunInspectorScreen(
                self.agent_client,
                "run-1",
                poll_interval=self.poll_interval,
            )
        )


@pytest.mark.asyncio
async def test_run_inspector_replays_canonical_events() -> None:
    app = _RunHarness(_FakeCapabilityClient())
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        inspector = app.screen
        assert isinstance(inspector, RunInspectorScreen)
        assert inspector.next_after == 2
        assert inspector.query_one(DataTable).row_count == 2


@pytest.mark.asyncio
async def test_mission_control_follows_through_graph_and_output_progress() -> None:
    client = _FollowClient(
        _run_page(0, _run_event(1, "graph_complete")),
        _run_page(
            1,
            _run_event(1, "graph_complete"),
            _run_event(2, "final_output"),
        ),
        _run_page(2, _run_event(3, "run_completed")),
    )
    app = _RunHarness(client)

    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        inspector = app.screen
        assert isinstance(inspector, RunInspectorScreen)
        assert client.requested_after == [0, 1, 2]
        assert [event.type for event in inspector.events] == [
            "graph_complete",
            "final_output",
            "run_completed",
        ]
        assert inspector.query_one(DataTable).row_count == 3
        assert inspector.terminal_event_type == "run_completed"
        assert inspector.next_after == 3
        assert not inspector.following


@pytest.mark.asyncio
async def test_mission_control_renders_gap_and_resumes_retained_events() -> None:
    client = _FollowClient(
        _run_page(
            0,
            _run_event(4, "graph_complete"),
            retained_from=4,
        ),
        _run_page(4, _run_event(5, "run_completed"), retained_from=4),
    )
    app = _RunHarness(client)

    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        inspector = app.screen
        assert isinstance(inspector, RunInspectorScreen)
        assert client.requested_after == [0, 4]
        assert len(inspector.replay_gaps) == 1
        assert inspector.replay_gaps[0].missing_from == 1
        assert inspector.replay_gaps[0].missing_through == 3
        assert "Replay reset: sequences 1-3" in str(
            inspector.query_one("#run-inspector-gap", Static).content
        )
        assert [event.sequence for event in inspector.events] == [4, 5]


class _RunBrowserHarness(App[None]):
    def __init__(self, client: _FakeCapabilityClient) -> None:
        super().__init__()
        self.agent_client = client

    def compose(self) -> ComposeResult:
        yield Static("harness")

    def on_mount(self) -> None:
        self.push_screen(RunBrowserScreen(self.agent_client, session_id="session-1"))


@pytest.mark.asyncio
async def test_run_browser_discovers_newest_lifecycle_summaries() -> None:
    app = _RunBrowserHarness(_FakeCapabilityClient())
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        browser = app.screen
        assert isinstance(browser, RunBrowserScreen)
        assert [run.run_id for run in browser.filtered] == ["run-1"]
        assert browser.filtered[0].status == "completed"
