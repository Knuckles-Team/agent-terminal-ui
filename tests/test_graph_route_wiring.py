"""Wiring tests for the ``/graph/*`` engine-surface routes.

``tests/test_engine_surface_commands.py`` drives the slash commands against a
fully mocked ``AgentClient``, so it cannot see where the client actually sends
its request — and the client was sending it to ``{base_url}/graph/...`` while
the gateway mounts the canonical KG route table under ``/api``
(``register_graph_routes(app, prefix="/api")``). Every engine-surface command
(``/ask``, ``/nl``, ``/obs``, ``/broker``, ``/kvcache``) therefore 404'd.

These tests put a real ``httpx`` transport under the real client and assert the
URL that leaves it, so the prefix cannot silently regress again.
"""

from __future__ import annotations

import asyncio

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
