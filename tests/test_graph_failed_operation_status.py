"""EH-386: the gateway answers a typed failed operation with non-2xx.

graph-os and AU REST twins return ``{"status": "failed", "result":
<OperationResult>}`` with the error code's HTTP status (400/403/500/503),
where they used to answer HTTP 200 ``"success"``. ``_graph_post`` keeps its
contract: a tool-level failure comes back as a result carrying ``error``, so
the command renders the tool's own message. A plain gateway failure still
raises.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from agent_terminal_ui.client import AgentClient
from agent_terminal_ui.commands import CommandProcessor

_FAILED = {
    "status": "failed",
    "operation_id": "op-1",
    "error": {
        "code": "permission_denied",
        "message": "The operation is not authorized.",
    },
}


def _client(status: int, body: object) -> AgentClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body, request=request)

    client = AgentClient("http://agent.test")
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def test_typed_failure_degrades_into_the_tool_result() -> None:
    client = _client(403, {"status": "failed", "result": _FAILED})
    result = asyncio.run(client.graph_nl_query("how many files"))
    assert result == _FAILED
    assert CommandProcessor._surface_error(result) == (
        "permission_denied: The operation is not authorized."
    )


def test_gateway_failure_without_an_envelope_still_raises() -> None:
    client = _client(502, {"detail": "bad gateway"})
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.graph_nl_query("how many files"))


def test_string_tool_error_is_unchanged() -> None:
    assert CommandProcessor._surface_error({"error": "no engine"}) == "no engine"
