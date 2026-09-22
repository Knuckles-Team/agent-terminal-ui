"""GraphOS A2A conversation transport of the terminal UI client."""

import json
from typing import Any

import httpx
import pytest

from agent_terminal_ui.client import A2ATransportError, AgentClient

_TASK = "a2a-" + "1" * 64
_CONTEXT = "a2a-context-" + "2" * 64


def _sse(*frames: dict[str, Any]) -> bytes:
    blocks = []
    for index, frame in enumerate(frames):
        blocks.append(f"id: e{index}\nevent: message\ndata: {json.dumps(frame)}\n\n")
    return "".join(blocks).encode()


def _result(result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": "message/stream", "result": result}


def _task(state: str) -> dict[str, Any]:
    return {
        "id": _TASK,
        "contextId": _CONTEXT,
        "kind": "task",
        "status": {"state": state},
        "metadata": {"graphOs": {"runId": _TASK}},
    }


def _status(state: str, *, final: bool) -> dict[str, Any]:
    return {
        "taskId": _TASK,
        "contextId": _CONTEXT,
        "kind": "status-update",
        "status": {"state": state},
        "final": final,
        "metadata": {"graphOs": {"runId": _TASK}},
    }


class _Recorder:
    def __init__(self, responder: Any) -> None:
        self.requests: list[httpx.Request] = []
        self._responder = responder

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._responder(request)


def _client(responder: Any, **kwargs: Any) -> tuple[AgentClient, _Recorder]:
    recorder = _Recorder(responder)
    client = AgentClient(base_url="http://graph-os.test", **kwargs)
    client._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(recorder),
        headers=client._http_client.headers,
    )
    return client, recorder


@pytest.mark.asyncio
async def test_stream_runs_one_authenticated_a2a_task_to_its_final_state():
    body = _sse(
        _result(_task("submitted")),
        _result(_status("working", final=False)),
        _result(
            {
                "taskId": _TASK,
                "contextId": _CONTEXT,
                "kind": "artifact-update",
                "artifact": {
                    "artifactId": f"{_TASK}:answer",
                    "parts": [{"kind": "text", "text": "the answer"}],
                },
                "lastChunk": True,
            }
        ),
        _result(_status("completed", final=True)),
    )
    client, recorder = _client(
        lambda request: httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        ),
        bearer_token="tok",
    )

    events = [event async for event in client.stream("hello", session_id="ctx-1")]

    request = recorder.requests[0]
    sent = json.loads(request.content)
    assert request.url.path == "/a2a"
    assert request.headers["Authorization"] == "Bearer tok"
    assert request.headers["Idempotency-Key"]
    assert sent["method"] == "message/stream"
    assert sent["params"]["message"]["contextId"] == "ctx-1"
    assert sent["params"]["message"]["parts"] == [{"kind": "text", "text": "hello"}]
    assert sent["params"]["message"]["metadata"] == {
        "graphOsTaskIris": ["eg:task/communicate"]
    }
    assert [event["type"] for event in events] == [
        "session_started",
        "sideband",
        "sideband",
        "text",
        "sideband",
        "turn_end",
    ]
    assert events[3]["content"] == "the answer"
    assert [e["data"]["state"] for e in events if e["type"] == "sideband"] == [
        "submitted",
        "working",
        "completed",
    ]
    assert all(event["session_id"] == "ctx-1" for event in events)
    assert events[-1]["run_id"] == _TASK
    assert client.current_task_id == _TASK
    await client.close()


@pytest.mark.asyncio
async def test_failed_task_reports_an_error_before_ending_the_turn():
    body = _sse(_result(_task("submitted")), _result(_status("failed", final=True)))
    client, _ = _client(lambda request: httpx.Response(200, content=body))

    events = [event async for event in client.stream("hello")]

    assert [event["type"] for event in events[-2:]] == ["error", "turn_end"]
    await client.close()


@pytest.mark.asyncio
async def test_unauthenticated_or_refused_stream_surfaces_one_error_event():
    client, _ = _client(
        lambda request: httpx.Response(
            503,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32003, "message": "assembly unavailable"},
            },
        )
    )

    events = [event async for event in client.stream("hello", session_id="s")]

    assert events[-1] == {
        "type": "error",
        "message": "assembly unavailable",
        "session_id": "s",
    }
    await client.close()


@pytest.mark.asyncio
async def test_error_frame_mid_stream_ends_the_turn_with_an_error():
    body = _sse(
        _result(_task("submitted")),
        {"jsonrpc": "2.0", "id": 1, "error": {"code": -32001, "message": "gone"}},
    )
    client, _ = _client(lambda request: httpx.Response(200, content=body))

    events = [event async for event in client.stream("hello", session_id="s")]

    assert events[-1]["type"] == "error" and events[-1]["message"] == "gone"
    await client.close()


@pytest.mark.asyncio
async def test_non_text_parts_are_refused_before_any_request():
    client, recorder = _client(lambda request: httpx.Response(500))

    events = [
        event
        async for event in client.stream("x", parts=[{"type": "image", "url": "u"}])
    ]

    assert events[-1]["type"] == "error"
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
async def test_cancel_targets_the_current_turns_task():
    body = _sse(_result(_task("working")))

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["method"] == "tasks/cancel":
            assert payload["params"] == {"id": _TASK}
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "result": _task("canceled")},
            )
        return httpx.Response(200, content=body)

    client, _ = _client(respond)
    [event async for event in client.stream("hello")]

    cancelled = await client.cancel_task()

    assert cancelled["status"]["state"] == "canceled"
    await client.close()


@pytest.mark.asyncio
async def test_cancel_without_a_task_is_refused_locally():
    client, recorder = _client(lambda request: httpx.Response(500))
    with pytest.raises(ValueError):
        await client.cancel_task()
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
async def test_cancel_error_raises_the_json_rpc_error():
    client, _ = _client(
        lambda request: httpx.Response(
            409,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32002, "message": "not cancelable"},
            },
        )
    )
    with pytest.raises(A2ATransportError) as caught:
        await client.cancel_task(_TASK)
    assert caught.value.code == -32002
    await client.close()


@pytest.mark.asyncio
async def test_resubscribe_sends_the_last_event_id():
    body = _sse(_result(_status("completed", final=True)))
    client, recorder = _client(lambda request: httpx.Response(200, content=body))

    events = [event async for event in client.resubscribe(_TASK, last_event_id="e0")]

    request = recorder.requests[0]
    assert json.loads(request.content)["method"] == "tasks/resubscribe"
    assert request.headers["Last-Event-ID"] == "e0"
    assert events[-1]["type"] == "turn_end"
    await client.close()


@pytest.mark.asyncio
async def test_tool_approval_decisions_are_refused_explicitly():
    client = AgentClient()
    events = [event async for event in client.send_decision({"c1": "accept"})]
    assert [event["type"] for event in events] == ["error"]
    await client.close()


@pytest.mark.asyncio
async def test_metadata_reads_the_agent_card():
    card = {"name": "GraphOS", "capabilities": {"streaming": True}}
    client, recorder = _client(lambda request: httpx.Response(200, json=card))

    assert await client.get_metadata() == card
    assert recorder.requests[0].url.path == "/.well-known/agent-card.json"
    await client.close()


# ``agent-client-protocol`` (Zed's ACP SDK) is not a dependency of this
# package: nothing in ``agent_terminal_ui`` imports ``agent_client_protocol``,
# and ``AgentClient`` must construct even when it is not importable at all.


def test_agent_client_protocol_module_is_not_imported_by_this_package():
    """``agent_client_protocol`` (the real Zed ACP SDK) must not be a runtime
    dependency of this client — conversation turns use GraphOS's A2A
    JSON-RPC/SSE boundary, not that SDK's wire format."""
    import ast
    from pathlib import Path

    import agent_terminal_ui

    package_dir = Path(agent_terminal_ui.__file__).parent
    for py_file in package_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            for name in names:
                assert name is None or not name.startswith("agent_client_protocol"), (
                    f"{py_file} imports agent_client_protocol at {node.lineno}"
                )


def test_agent_client_constructs_with_agent_client_protocol_hidden(monkeypatch):
    """Simulate the dependency being absent entirely (uninstalled): importing
    and constructing ``AgentClient`` must not require it."""
    import builtins

    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name == "agent_client_protocol" or name.startswith("agent_client_protocol."):
            raise ModuleNotFoundError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)

    # Re-import fresh to prove construction doesn't reach for the SDK.
    import importlib

    import agent_terminal_ui.client as client_module

    importlib.reload(client_module)
    client = client_module.AgentClient(base_url="http://localhost:8000")
    assert client.base_url == "http://localhost:8000"
    assert client.a2a_url == "http://localhost:8000/a2a"
