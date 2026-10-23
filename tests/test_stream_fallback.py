"""Unsupported streaming never permits replay of an acknowledged task."""

import json
from collections.abc import AsyncIterator

import httpx
import pytest

from agent_terminal_ui.client import AgentClient

pytestmark = pytest.mark.spec("TUI-RUNTIME-R002.1.7")
CODES = [-32010, -32004, -32601]


@pytest.fixture
async def client() -> AsyncIterator[AgentClient]:
    value = AgentClient("http://localhost:8000", bearer_token="fixture-token")
    await value._http_client.aclose()
    yield value
    await value.close()


def bind(client, error_code, *, result=None, status=200, root_unary=False, mixed=False):
    requests = []

    def respond(request):
        requests.append(request)
        if request.method == "GET":
            assert request.url.path == "/.well-known/agent-card.json"
            return httpx.Response(
                200, json={"capabilities": {"streaming": not root_unary}}
            )
        method = json.loads(request.content)["method"]
        if method == "message/stream":
            error = {"error": {"code": error_code, "message": "refused"}}
            if mixed:
                error["result"] = {}
            if status != 200:
                return httpx.Response(status, json=error)
            frames = ([] if result is None else [{"result": result}]) + [error]
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                text="".join("data: " + json.dumps(f) + "\n\n" for f in frames),
            )
        assert method == "message/send"
        return httpx.Response(
            200,
            json={
                "result": {
                    "kind": "task",
                    "id": "unary-task",
                    "contextId": "a2a-context-" + "1" * 64,
                    "metadata": {"arbora": {"runId": "unary-task"}},
                    "status": {"state": "completed"},
                    "history": [
                        {"role": "agent", "parts": [{"kind": "text", "text": "answer"}]}
                    ],
                }
            },
        )

    client._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        headers={"Authorization": "Bearer fixture-token"},
    )
    return requests


@pytest.mark.asyncio
@pytest.mark.parametrize("code", CODES)
@pytest.mark.parametrize("status", [200, 501])
async def test_explicit_unsupported_before_result_falls_back_once(client, code, status):
    requests = bind(client, code, status=status)
    events = [event async for event in client.stream("hello")]
    posts = [r for r in requests if r.method == "POST"]
    assert [json.loads(r.content)["method"] for r in posts] == [
        "message/stream",
        "message/send",
    ]
    assert posts[0].headers["Idempotency-Key"] == posts[1].headers["Idempotency-Key"]
    streaming = json.loads(posts[0].content)["params"]
    unary = json.loads(posts[1].content)["params"]
    assert unary == {**streaming, "configuration": {"blocking": False}}
    assert all(r.headers["Authorization"] == "Bearer fixture-token" for r in requests)
    assert [e["content"] for e in events if e["type"] == "text"] == ["answer"]


@pytest.mark.asyncio
@pytest.mark.parametrize("code", CODES)
@pytest.mark.parametrize(
    "result",
    [
        {},
        {
            "kind": "artifact-update",
            "taskId": "accepted-task",
            "artifact": {"parts": []},
        },
        {
            "kind": "status-update",
            "taskId": "accepted-task",
            "status": {"state": "working"},
        },
    ],
)
async def test_any_raw_acknowledgment_blocks_unary_replay(client, code, result):
    requests = bind(client, code, result=result)
    events = [event async for event in client.stream("hello")]
    assert [
        json.loads(r.content)["method"] for r in requests if r.method == "POST"
    ] == ["message/stream"]
    assert events[-1]["type"] == "error"
    if result.get("taskId"):
        assert client.current_task_id == "accepted-task"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code,status",
    [
        (-32001, 200),
        (-32001, 401),
        (-32001, 403),
        (-32010, 401),
        (-32004, 403),
        (-32601, 401),
    ],
)
async def test_permission_denial_never_retries(client, code, status):
    requests = bind(client, code, status=status)
    events = [event async for event in client.stream("hello")]
    assert [
        json.loads(r.content)["method"] for r in requests if r.method == "POST"
    ] == ["message/stream"]
    assert events[-1]["type"] == "error"


@pytest.mark.asyncio
async def test_merged_root_discovery_avoids_stream_attempt(client):
    requests = bind(client, -32010, root_unary=True)
    events = [event async for event in client.stream("hello")]
    assert [
        json.loads(r.content)["method"] for r in requests if r.method == "POST"
    ] == ["message/send"]
    assert any(e.get("content") == "answer" for e in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 501])
async def test_ambiguous_result_and_error_never_permits_replay(client, status):
    requests = bind(client, -32601, status=status, mixed=True)
    events = [event async for event in client.stream("hello")]
    assert len([r for r in requests if r.method == "POST"]) == 1
    assert events[-1]["type"] == "error"


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [-32601.0, "-32601", None, [], {}])
async def test_malformed_code_never_permits_replay(client, code):
    requests = bind(client, code)
    events = [event async for event in client.stream("hello")]
    assert len([r for r in requests if r.method == "POST"]) == 1
    assert events[-1]["type"] == "error"
