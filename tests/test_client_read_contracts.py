"""Consumer contract evidence; no live producer or conversation-resume proof."""

import json
from collections.abc import AsyncIterator, Callable
from typing import Any, get_type_hints

import httpx
import pytest
import pytest_asyncio
from arbora.client._generated_models import REGISTRY_DIGEST

from agent_terminal_ui.client import (
    A2ATransportError,
    AgentClient,
    ArboraOperationError,
)
from tests.test_task_history import task

pytestmark = [pytest.mark.spec("TUI-RUNTIME-R015.50")]


@pytest_asyncio.fixture
async def read_client() -> AsyncIterator[
    tuple[AgentClient, list[httpx.Request], list[Any]]
]:
    requests: list[httpx.Request] = []
    replies: list[Any] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer fixture-caller"
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    client = AgentClient(
        base_url="https://arbora.example", bearer_token="fixture-caller"
    )
    headers = dict(client._http_client.headers)
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(serve),
        headers=headers,
    )
    client._current_session_id = "active-context"
    client._current_task_id = "active-task"
    try:
        yield client, requests, replies
    finally:
        await client.close()


def operation(value: Any) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "ok": True,
            "result": {"value": value},
            "meta": {"registry_digest": REGISTRY_DIGEST},
        },
    )


def history(value: Any) -> httpx.Response:
    return httpx.Response(
        200, json={"jsonrpc": "2.0", "id": "fixture", "result": value}
    )


READS = [
    pytest.param(
        "get_mcp_config",
        "/api/v1/ops/fleet.status",
        {"children": {}},
        operation,
        id="status",
        marks=pytest.mark.spec("TUI-RUNTIME-R015.44"),
    ),
    pytest.param(
        "list_mcp_tools",
        "/api/v1/ops/fleet.catalog.list",
        {"items": [], "next_cursor": None},
        operation,
        id="tools",
        marks=pytest.mark.spec("TUI-RUNTIME-R015.45"),
    ),
    pytest.param(
        "list_history_tasks",
        "/a2a",
        {"tasks": [], "nextCursor": None},
        history,
        id="contexts",
        marks=pytest.mark.spec("TUI-RUNTIME-R015.46"),
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,empty,encode", READS)
@pytest.mark.spec("TUI-RUNTIME-R015.47")
async def test_authenticated_empty_is_success_without_context_change(
    read_client, method, path, empty, encode
) -> None:
    client, requests, replies = read_client
    replies.append(encode(empty))
    result = await getattr(client, method)()
    assert result == ([] if method == "list_mcp_tools" else empty)
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == path
    body = json.loads(requests[0].content)
    expected = {
        "get_mcp_config": {},
        "list_mcp_tools": {"browse": True, "kinds": ["tool"], "limit": 100},
    }
    if method == "list_history_tasks":
        assert body["method"] == "tasks/list"
        assert body["params"] == {"limit": 50}
    else:
        assert body == expected[method]
    assert (client.current_session_id, client.current_task_id) == (
        "active-context",
        "active-task",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,empty,encode", READS)
@pytest.mark.parametrize(
    "fault", ["denied", "unavailable", "malformed", "timeout", "disconnect"]
)
@pytest.mark.spec("TUI-RUNTIME-R015.47")
async def test_failed_read_after_success_never_becomes_empty_or_falls_back(
    read_client, method, path, empty, encode, fault
) -> None:
    client, requests, replies = read_client
    values: dict[str, dict[str, Any]] = {
        "get_mcp_config": {"children": {"visible": {}}},
        "list_mcp_tools": {
            "items": [{"id": "one", "name": "tool", "description": "visible"}],
            "next_cursor": None,
        },
        "list_history_tasks": {"tasks": [task(1)], "nextCursor": None},
    }
    value = values[method]
    replies.append(encode(value))
    result = await getattr(client, method)()
    assert result == (value["items"] if method == "list_mcp_tools" else value)
    if fault in {"timeout", "disconnect"}:
        replies.append(
            httpx.ReadTimeout("fixture timeout")
            if fault == "timeout"
            else httpx.ConnectError("fixture disconnect")
        )
    elif fault == "malformed":
        replies.append(encode([]))
    elif method == "list_history_tasks":
        replies.append(
            httpx.Response(
                403 if fault == "denied" else 503,
                json={
                    "jsonrpc": "2.0",
                    "id": "fixture",
                    "error": {"code": -32001, "message": fault},
                },
            )
        )
    else:
        replies.append(
            httpx.Response(
                403 if fault == "denied" else 503,
                json={
                    "ok": False,
                    "error": {"code": fault.upper()},
                    "meta": {"registry_digest": REGISTRY_DIGEST},
                },
            )
        )
    expected_error = (
        httpx.ReadTimeout
        if fault == "timeout"
        else httpx.ConnectError
        if fault == "disconnect"
        else A2ATransportError
        if method == "list_history_tasks"
        else ArboraOperationError
    )
    with pytest.raises(expected_error) as caught:
        await getattr(client, method)()
    if isinstance(caught.value, ArboraOperationError):
        assert caught.value.code == (
            "INVALID_ENVELOPE" if fault == "malformed" else fault.upper()
        )
    elif isinstance(caught.value, A2ATransportError) and fault != "malformed":
        assert caught.value.code == -32001
    assert len(requests) == 2
    assert {r.url.path for r in requests} == {path}
    assert (client.current_session_id, client.current_task_id) == (
        "active-context",
        "active-task",
    )


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R015.45")
@pytest.mark.parametrize("fault", ["denied", "timeout", "malformed", "cycle", "limit"])
async def test_catalog_partial_page_is_never_returned(read_client, fault) -> None:
    client, requests, replies = read_client
    item = {"id": "one", "name": "visible", "description": "description"}
    replies.append(operation({"items": [item], "next_cursor": "opaque / + cursor"}))
    if fault == "denied":
        replies.append(
            httpx.Response(
                403,
                json={
                    "ok": False,
                    "error": {"code": "DENIED"},
                    "meta": {"registry_digest": REGISTRY_DIGEST},
                },
            )
        )
    elif fault == "timeout":
        replies.append(httpx.ReadTimeout("fixture timeout"))
    elif fault == "malformed":
        replies.append(operation({"items": [{"id": "bad"}], "next_cursor": None}))
    elif fault == "cycle":
        replies.append(operation({"items": [], "next_cursor": "opaque / + cursor"}))
    else:
        replies.extend(
            operation({"items": [], "next_cursor": f"page-{n}"}) for n in range(9)
        )
    with pytest.raises((ArboraOperationError, httpx.ReadTimeout)):
        await client.list_mcp_tools()
    assert len(requests) == (10 if fault == "limit" else 2)
    assert json.loads(requests[1].content)["cursor"] == "opaque / + cursor"
    assert all(r.url.path == "/api/v1/ops/fleet.catalog.list" for r in requests)


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R015.46")
async def test_context_identifiers_follow_served_pages_without_inventing_grouping(
    read_client,
) -> None:
    client, requests, replies = read_client
    first = [task(1), {**task(2), "contextId": "context-1"}]
    second = [task(3)]
    replies.extend(
        [
            history({"tasks": first, "nextCursor": "opaque / + cursor"}),
            history({"tasks": second, "nextCursor": None}),
        ]
    )
    page = await client.list_history_tasks()
    assert [t["contextId"] for t in page["tasks"]] == ["context-1", "context-1"]
    following = await client.list_history_tasks(page["nextCursor"])
    assert [t["contextId"] for t in following["tasks"]] == ["context-3"]
    assert json.loads(requests[1].content)["params"] == {
        "limit": 50,
        "cursor": "opaque / + cursor",
    }
    assert (client.current_session_id, client.current_task_id) == (
        "active-context",
        "active-task",
    )


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R015.44")
@pytest.mark.parametrize(
    "value", [{}, {"children": []}, {"children": None}, {"children": "invalid"}]
)
async def test_status_rejects_malformed_children(read_client, value) -> None:
    client, requests, replies = read_client
    replies.append(operation(value))
    with pytest.raises(ArboraOperationError, match="INVALID_ENVELOPE"):
        await client.get_mcp_config()
    assert len(requests) == 1


@pytest.mark.spec("TUI-RUNTIME-R015.49")
@pytest.mark.parametrize(
    "method,expected",
    [
        (AgentClient.get_mcp_config, dict[str, Any]),
        (AgentClient.list_mcp_tools, list[dict[str, Any]]),
        (AgentClient.list_history_tasks, dict[str, Any]),
    ],
)
def test_production_read_signatures(method: Callable[..., Any], expected: Any) -> None:
    assert get_type_hints(method)["return"] == expected
    if method is AgentClient.list_history_tasks:
        assert get_type_hints(method)["cursor"] == str | None


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R015.45")
@pytest.mark.parametrize(
    "value",
    [
        {"items": [], "next_cursor": ""},
        {"items": [], "next_cursor": "x" * 1025},
        {"items": [], "next_cursor": 3},
        {"items": [{}], "next_cursor": None},
        {
            "items": [{"id": "one", "name": 3, "description": "text"}],
            "next_cursor": None,
        },
        {
            "items": [{"id": "one", "name": "name", "description": None}],
            "next_cursor": None,
        },
        {"items": [{}] * 101, "next_cursor": None},
    ],
)
async def test_catalog_rejects_invalid_page_fields(read_client, value) -> None:
    client, requests, replies = read_client
    replies.append(operation(value))
    with pytest.raises(ArboraOperationError, match="INVALID_ENVELOPE"):
        await client.list_mcp_tools()
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R015.46")
@pytest.mark.parametrize(
    "value",
    [
        {"tasks": [{**task(1), "contextId": ""}]},
        {"tasks": [{**task(1), "contextId": 1}]},
        {"tasks": [task(1), task(1)]},
        {"tasks": [task(1)] * 51},
        {"tasks": [], "nextCursor": ""},
        {"tasks": [], "nextCursor": 1},
    ],
)
async def test_context_pages_reject_invalid_identity_and_bounds(
    read_client, value
) -> None:
    client, requests, replies = read_client
    replies.append(history(value))
    with pytest.raises(ValueError):
        await client.list_history_tasks()
    assert len(requests) == 1
    assert (client.current_session_id, client.current_task_id) == (
        "active-context",
        "active-task",
    )
