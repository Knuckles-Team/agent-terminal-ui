"""GraphOS A2A conversation transport of the terminal UI client."""

import ast
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from agent_terminal_ui.client import (
    A2ATransportError,
    AgentClient,
    GraphOSOperationError,
    client_from_environment,
)

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
    client = AgentClient(base_url="http://localhost:8000", **kwargs)
    client._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(recorder),
        headers=client._http_client.headers,
    )
    return client, recorder


def _registry_digest() -> str:
    from graph_os.client._generated_models import REGISTRY_DIGEST

    return REGISTRY_DIGEST


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example:8000",
        "https://user:password@remote.example",
        "https://remote.example?token=secret",
        "https://remote.example#fragment",
        "https://remote.example/api",
        "https://remote.example:99999",
        " https://remote.example",
        "https://remote.example\n",
        "https://local\nhost",
        "https://remote.example\\path",
    ],
)
@pytest.mark.spec("TUI-RUNTIME-R001.2")
def test_graphos_endpoint_refuses_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        AgentClient(base_url=url, bearer_token="caller-token")


@pytest.mark.parametrize(
    "token", ["", " ", "token\nvalue", "token\tvalue", "tok\u00e9n"]
)
@pytest.mark.spec("TUI-RUNTIME-R001.2")
def test_graphos_client_rejects_invalid_caller_credential(token: str) -> None:
    with pytest.raises(ValueError, match="invalid caller credential"):
        AgentClient(base_url="https://remote.example", bearer_token=token)


@pytest.mark.spec("TUI-RUNTIME-R001.2")
def test_remote_graphos_endpoint_requires_explicit_caller_credential() -> None:
    with pytest.raises(ValueError, match="requires caller credential"):
        AgentClient(base_url="https://remote.example")


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.2")
async def test_remote_graphos_environment_requires_operator_credential(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENT_URL", "https://remote.example")
    monkeypatch.delenv("AGENT_BEARER_TOKEN", raising=False)
    with pytest.raises(ValueError, match="requires caller credential"):
        client_from_environment()

    monkeypatch.setenv("AGENT_BEARER_TOKEN", "operator-token")
    client = client_from_environment()
    assert client._http_client.headers["Authorization"] == "Bearer operator-token"
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R002")
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
@pytest.mark.spec("TUI-RUNTIME-R001.4")
async def test_failed_task_reports_an_error_before_ending_the_turn():
    body = _sse(_result(_task("submitted")), _result(_status("failed", final=True)))
    client, _ = _client(lambda request: httpx.Response(200, content=body))

    events = [event async for event in client.stream("hello")]

    assert [event["type"] for event in events[-2:]] == ["error", "turn_end"]
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.4")
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
@pytest.mark.spec("TUI-RUNTIME-R001.4")
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
@pytest.mark.spec("TUI-RUNTIME-R002")
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
@pytest.mark.spec("TUI-RUNTIME-R002")
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
@pytest.mark.spec("TUI-RUNTIME-R002")
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
async def test_versioned_operation_preserves_refusal_details():
    client, recorder = _client(
        lambda request: httpx.Response(
            428,
            json={
                "ok": False,
                "error": {
                    "code": "STEP_UP_REQUIRED",
                    "details": {"console_url": "/console/confirm/plan"},
                },
                "meta": {"registry_digest": _registry_digest()},
            },
        )
    )
    with pytest.raises(GraphOSOperationError) as caught:
        await client.invoke_op("query.uql", {"query": "MATCH ()"})
    assert caught.value.code == "STEP_UP_REQUIRED"
    assert caught.value.details["console_url"] == "/console/confirm/plan"
    assert recorder.requests[0].url.path == "/api/v1/ops/query.uql"
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.1")
async def test_versioned_operation_uses_generated_digest_contract() -> None:
    client, recorder = _client(
        lambda _request: httpx.Response(
            200,
            json={
                "ok": True,
                "result": {"rows": [1]},
                "meta": {"registry_digest": _registry_digest()},
            },
        )
    )
    assert await client.invoke_op("query.uql", {"query": "MATCH ()"}) == {"rows": [1]}
    assert recorder.requests[0].url.path == "/api/v1/ops/query.uql"
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.1")
async def test_versioned_operation_rejects_stale_registry() -> None:
    client, _recorder = _client(
        lambda _request: httpx.Response(
            200,
            json={
                "ok": True,
                "result": {},
                "meta": {"registry_digest": "stale"},
            },
        )
    )
    with pytest.raises(GraphOSOperationError) as caught:
        await client.invoke_op("query.uql", {})
    assert caught.value.code == "REGISTRY_MISMATCH"
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.1")
async def test_versioned_operation_rejects_unregistered_op_before_network() -> None:
    client, recorder = _client(lambda _request: httpx.Response(500))
    with pytest.raises(GraphOSOperationError) as caught:
        await client.invoke_op("unregistered.action", {})
    assert caught.value.code == "UNKNOWN_OP"
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.6")
async def test_versioned_operation_refuses_python_311_without_network(
    monkeypatch,
) -> None:
    import agent_terminal_ui.client as client_module

    monkeypatch.setattr(client_module, "sys", SimpleNamespace(version_info=(3, 11)))
    client, recorder = _client(lambda _request: httpx.Response(500))
    with pytest.raises(GraphOSOperationError) as caught:
        await client.invoke_op("query.uql", {})
    assert caught.value.code == "CLIENT_UNAVAILABLE"
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.6")
async def test_python_311_keeps_a2a_chat_when_ops_client_is_unavailable(
    monkeypatch,
) -> None:
    import agent_terminal_ui.client as client_module

    monkeypatch.setattr(client_module, "sys", SimpleNamespace(version_info=(3, 11)))
    body = _sse(_result(_task("submitted")), _result(_status("completed", final=True)))
    client, recorder = _client(lambda _request: httpx.Response(200, content=body))
    events = [event async for event in client.stream("hello", session_id="ctx-1")]
    assert events[-1]["type"] == "turn_end"
    assert json.loads(recorder.requests[0].content)["method"] == "message/stream"
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.1")
async def test_versioned_operation_refuses_incomplete_client_wheel(
    monkeypatch,
) -> None:
    import graph_os.client._generated_models as models

    def missing_registry(_op: str) -> None:
        raise FileNotFoundError("registry.json")

    monkeypatch.setattr(models, "schema_for", missing_registry)
    client, recorder = _client(lambda _request: httpx.Response(500))
    with pytest.raises(GraphOSOperationError) as caught:
        await client.invoke_op("query.uql", {})
    assert caught.value.code == "CLIENT_UNAVAILABLE"
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("op", ["approvals.grant", "Approvals.Deny"])
async def test_approval_operation_is_refused_before_network(op: str):
    client, recorder = _client(lambda _request: httpx.Response(500))
    with pytest.raises(GraphOSOperationError) as caught:
        await client.invoke_op(op, {"approval_id": "a1"})
    assert caught.value.code == "APPROVAL_UNAVAILABLE"
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "op", ["query/uql", "query..uql", "query.uql?x=1", "query.uql\n", ""]
)
@pytest.mark.spec("TUI-RUNTIME-R001.1")
async def test_versioned_operation_refuses_unsafe_ids_without_network(op: str):
    client, recorder = _client(
        lambda _request: httpx.Response(200, json={"ok": True, "result": {}})
    )
    with pytest.raises(ValueError, match="operation id"):
        await client.invoke_op(op, {})
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", ["non_json", "missing_result"])
@pytest.mark.spec("TUI-RUNTIME-R001.1")
async def test_versioned_operation_refuses_malformed_success_envelope(
    malformed: str,
):
    response = (
        httpx.Response(200, text="not JSON")
        if malformed == "non_json"
        else httpx.Response(
            200,
            json={
                "ok": True,
                "meta": {"registry_digest": _registry_digest()},
            },
        )
    )
    client, _recorder = _client(lambda _request: response)
    with pytest.raises(GraphOSOperationError) as caught:
        await client.invoke_op("query.uql", {"query": "MATCH ()"})
    assert caught.value.code == "INVALID_ENVELOPE"
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.3")
async def test_confirm_plan_sends_full_binding():
    client, recorder = _client(
        lambda request: httpx.Response(
            200, json={"jsonrpc": "2.0", "result": {"done": True}}
        ),
        bearer_token="caller-token",
    )
    assert await client.confirm_plan(
        plan_ref="p1", op="query.uql", params={"query": "MATCH ()"}
    ) == {"done": True}
    sent = json.loads(recorder.requests[0].content)
    assert sent["method"] == "graphos.plan/confirm"
    assert sent["params"]["params"] == {"query": "MATCH ()"}
    assert recorder.requests[0].headers["Authorization"] == "Bearer caller-token"
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.3")
async def test_unsigned_plan_confirmation_refuses_before_network():
    client, recorder = _client(lambda _request: httpx.Response(500))
    with pytest.raises(GraphOSOperationError) as caught:
        await client.confirm_plan(
            plan_ref="p1", op="query.uql", params={"query": "MATCH ()"}
        )
    assert caught.value.code == "CALLER_CREDENTIAL_REQUIRED"
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.5")
async def test_unsigned_input_required_decision_cannot_resume_a2a_task():
    client, recorder = _client(lambda _request: httpx.Response(500))
    client._pending_plans[_TASK] = {
        "plan_ref": "p1",
        "op": "query.uql",
        "params": {"query": "MATCH ()"},
    }
    events = [event async for event in client.send_decision({_TASK: "accept"})]
    assert events[-1]["type"] == "error"
    assert events[-1]["message"] == "CALLER_CREDENTIAL_REQUIRED"
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.3")
async def test_confirm_plan_refuses_approval_operation_without_network():
    client, recorder = _client(lambda _request: httpx.Response(500))
    with pytest.raises(GraphOSOperationError) as caught:
        await client.confirm_plan(
            plan_ref="p1", op="approvals.grant", params={"approval_id": "a1"}
        )
    assert caught.value.code == "APPROVAL_UNAVAILABLE"
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.5")
async def test_task_input_required_exposes_only_bound_approval():
    bound = _status("input-required", final=False)
    bound["status"]["message"] = {
        "metadata": {
            "graphOsPlan": {
                "plan_ref": "p1",
                "op": "query.uql",
                "params": {"query": "MATCH ()"},
                "confirm": "plan",
            }
        }
    }
    client, _ = _client(
        lambda request: httpx.Response(200, content=_sse(_result(bound)))
    )
    events = [event async for event in client.stream("hello", session_id="ctx-1")]
    assert [event["type"] for event in events][-2:] == ["tool_call", "turn_end"]
    assert client._pending_plans[_TASK]["params"] == {"query": "MATCH ()"}
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.5")
async def test_unbound_input_required_fails_closed():
    client, _ = _client(
        lambda request: httpx.Response(
            200, content=_sse(_result(_status("input-required", final=False)))
        )
    )
    events = [event async for event in client.stream("hello", session_id="ctx-1")]
    assert events[-1]["type"] == "error"
    assert _TASK not in client._pending_plans
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.5")
async def test_console_input_required_cannot_offer_tui_approval():
    console = _status("input-required", final=False)
    console["status"]["message"] = {
        "metadata": {
            "graphOsPlan": {
                "plan_ref": "p1",
                "op": "approvals.grant",
                "params": {"approval_id": "a1"},
                "confirm": "console",
            }
        }
    }
    client, _ = _client(
        lambda request: httpx.Response(200, content=_sse(_result(console)))
    )
    events = [event async for event in client.stream("hello", session_id="ctx-1")]
    assert events[-1]["type"] == "error"
    assert _TASK not in client._pending_plans
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.5")
async def test_forged_plan_binding_cannot_offer_approval_operation():
    forged = _status("input-required", final=False)
    forged["status"]["message"] = {
        "metadata": {
            "graphOsPlan": {
                "plan_ref": "p1",
                "op": "approvals.grant",
                "params": {"approval_id": "a1"},
                "confirm": "plan",
            }
        }
    }
    client, _ = _client(
        lambda _request: httpx.Response(200, content=_sse(_result(forged)))
    )
    events = [event async for event in client.stream("hello", session_id="ctx-1")]
    assert events[-1]["type"] == "error"
    assert _TASK not in client._pending_plans
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


def _imported_module_names(node: ast.AST) -> list[str | None]:
    """Names imported by one `Import`/`ImportFrom` AST node (else empty)."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return [node.module] if node.module else []
    return []


def _assert_no_agent_client_protocol_import(py_file: Path) -> None:
    """Assert one source file never imports ``agent_client_protocol``."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for name in _imported_module_names(node):
            location = getattr(node, "lineno", "?")
            assert name is None or not name.startswith("agent_client_protocol"), (
                f"{py_file} imports agent_client_protocol at {location}"
            )


@pytest.mark.spec("TUI-RUNTIME-R001.7")
def test_agent_client_protocol_module_is_not_imported_by_this_package():
    """``agent_client_protocol`` (the real Zed ACP SDK) must not be a runtime
    dependency of this client — conversation turns use GraphOS's A2A
    JSON-RPC/SSE boundary, not that SDK's wire format."""
    import agent_terminal_ui

    package_dir = Path(agent_terminal_ui.__file__).parent
    for py_file in package_dir.rglob("*.py"):
        _assert_no_agent_client_protocol_import(py_file)


def test_agent_client_constructs_with_agent_client_protocol_hidden():
    """Simulate the dependency being absent entirely (uninstalled): importing
    and constructing ``AgentClient`` must not require it."""
    script = """
import builtins
real_import = builtins.__import__
def blocking_import(name, *args, **kwargs):
    if name == 'agent_client_protocol' or name.startswith('agent_client_protocol.'):
        raise ModuleNotFoundError(name)
    return real_import(name, *args, **kwargs)
builtins.__import__ = blocking_import
from agent_terminal_ui.client import AgentClient
client = AgentClient(base_url='http://localhost:8000')
assert client.a2a_url == 'http://localhost:8000/a2a'
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True)
