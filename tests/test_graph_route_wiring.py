"""Wiring tests for the ``/graph/*`` engine-surface routes.

``tests/test_engine_surface_commands.py`` drives the slash commands against a
fully mocked ``AgentClient``, so it cannot see where the client actually sends
its request — and the client was sending it to ``{base_url}/graph/...`` while
the gateway mounts the canonical KG route table under ``/api``
(``register_graph_routes(app, prefix="/api")``). Every engine-surface command
(``/ask``, ``/nl``, ``/obs``, ``/broker``, ``/kvcache``) therefore 404'd.

These tests put a real ``httpx`` transport under the real client and assert the
URL that leaves it, so the prefix cannot silently regress again.

D-FE-8 (partial remediation): this file originally covered only
``graph_nl_query``/``graph_ask_data``/``graph_promql`` (the regression that
motivated it). It has since been extended to also drive ``graph_broker``
(the riskiest body shape here -- ``params`` is conditionally re-encoded as a
``params_json`` *string* value, not forwarded as nested JSON), ``graph_traces``
(four independently-optional filter kwargs that must each be omitted from the
body when falsy), and ``graph_kvcache`` at the real-transport level, so a
wrong path, wrong method, or malformed body for any of the six ``/graph/*``
engine-surface methods on ``AgentClient`` fails a real test, not just a mock
assertion. The full command suite still has command-dispatch coverage only
(mocked ``AgentClient``) for everything outside these six methods -- e.g.
capability invocation, run inspection, dashboard, KB, memory, prompts, SDD,
cron, and MCP-config commands in ``tests/test_engine_surface_commands.py`` and
sibling command-test files remain mock-only. Converting the whole command
suite to drive a real transport is explicitly out of scope for this pass
(see ``reports/deferred/lane-frontends.md`` D-FE-8) and is left for whoever
picks up the remainder.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from agent_terminal_ui.client import AgentClient


class _RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, result: dict | None = None) -> None:
        self.result = result if result is not None else {"surface": "ok"}
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            200,
            json={"status": "success", "result": self.result},
            request=request,
        )


def _client_with(transport: httpx.AsyncBaseTransport) -> AgentClient:
    client = AgentClient("http://agent.test")
    client._http_client = httpx.AsyncClient(transport=transport, timeout=5.0)
    return client


@pytest.mark.parametrize(
    ("call", "expected_path"),
    [
        (lambda c: c.graph_nl_query("how many files"), "/api/graph/nl-query"),
        (lambda c: c.graph_ask_data("how many files"), "/api/graph/ask-data"),
        (lambda c: c.graph_promql("up"), "/api/graph/promql"),
    ],
)
def test_engine_surface_calls_reach_the_gateway_mounted_path(
    call, expected_path: str
) -> None:
    transport = _RecordingTransport()
    client = _client_with(transport)

    asyncio.run(call(client))

    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url.path == expected_path
    # The un-prefixed path is what used to be sent and is served by nothing.
    assert request.url.path.startswith("/api/")


def test_the_unwrapped_result_reaches_the_caller() -> None:
    transport = _RecordingTransport({"surface": "promql", "result": [{"value": 1}]})
    client = _client_with(transport)

    payload = asyncio.run(client.graph_promql("up"))

    assert payload == {"surface": "promql", "result": [{"value": 1}]}


def test_a_gateway_404_is_raised_rather_than_read_as_an_empty_result() -> None:
    """A missing route must not look like "the engine returned nothing"."""

    class _NotFound(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"detail": "Not Found"}, request=request)

    client = _client_with(_NotFound())

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.graph_promql("up"))


def test_the_servers_own_unprefixed_routers_keep_their_paths() -> None:
    """``/models``/``/chats``/``/tools``/``/mcp/*`` are NOT under ``/api``.

    They are served by ``agent_utilities.server.routers`` directly, so the
    prefix belongs only to the canonical KG table.
    """
    transport = _RecordingTransport()

    class _Json(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            transport.requests.append(request)
            return httpx.Response(200, json=[], request=request)

    client = _client_with(_Json())

    asyncio.run(client.list_tools())

    assert transport.requests[-1].url.path == "/tools"


# ── D-FE-8 extension: graph_broker / graph_traces / graph_kvcache ─────────


def test_graph_broker_reaches_the_gateway_mounted_path_with_no_params() -> None:
    transport = _RecordingTransport()
    client = _client_with(transport)

    asyncio.run(client.graph_broker(action="stats"))

    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/api/graph/broker"
    body = json.loads(request.content)
    assert body == {"action": "stats"}
    # A missing ``params`` kwarg must not leak a "params_json": null/"{}" key.
    assert "params_json" not in body


def test_graph_broker_encodes_params_as_a_json_string_not_nested_json() -> None:
    """``params`` is re-encoded into a ``params_json`` *string* field.

    A regression that forwarded ``params`` as nested JSON (instead of a
    JSON-encoded string under ``params_json``) would send a body the gateway
    tool schema does not accept -- this pins the actual wire shape.
    """
    transport = _RecordingTransport()
    client = _client_with(transport)

    asyncio.run(
        client.graph_broker(action="list_queues", params={"exchange": "kg.events"})
    )

    request = transport.requests[0]
    assert request.url.path == "/api/graph/broker"
    body = json.loads(request.content)
    assert body["action"] == "list_queues"
    assert isinstance(body["params_json"], str)
    assert json.loads(body["params_json"]) == {"exchange": "kg.events"}


def test_graph_traces_omits_unset_optional_filters_from_the_body() -> None:
    """Falsy filter kwargs must not appear as empty-string keys in the body.

    A regression that always emitted ``trace_id``/``service``/``operation``/
    ``query`` (even as ``""``) would change the request shape the gateway
    tool schema validates against.
    """
    transport = _RecordingTransport()
    client = _client_with(transport)

    asyncio.run(client.graph_traces(service="agent-utilities"))

    request = transport.requests[0]
    assert request.url.path == "/api/graph/traces"
    body = json.loads(request.content)
    assert body == {"action": "search", "limit": 20, "service": "agent-utilities"}
    assert "trace_id" not in body
    assert "operation" not in body
    assert "query" not in body


def test_graph_traces_get_by_id_sends_only_the_trace_id_filter() -> None:
    transport = _RecordingTransport()
    client = _client_with(transport)

    asyncio.run(client.graph_traces(action="get", trace_id="abc123", limit=1))

    request = transport.requests[0]
    assert request.url.path == "/api/graph/traces"
    body = json.loads(request.content)
    assert body == {"action": "get", "limit": 1, "trace_id": "abc123"}


def test_graph_kvcache_reaches_the_gateway_mounted_path() -> None:
    transport = _RecordingTransport()
    client = _client_with(transport)

    asyncio.run(client.graph_kvcache(action="stats"))

    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/api/graph/kvcache"
    assert json.loads(request.content) == {"action": "stats"}
