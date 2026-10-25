"""Arbora A2A conversation transport of the terminal UI client."""

import ast
import base64
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
    ArboraOperationError,
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
        "metadata": {"arbora": {"runId": _TASK}},
    }


def _status(state: str, *, final: bool) -> dict[str, Any]:
    return {
        "taskId": _TASK,
        "contextId": _CONTEXT,
        "kind": "status-update",
        "status": {"state": state},
        "final": final,
        "metadata": {"arbora": {"runId": _TASK}},
    }


class _Recorder:
    def __init__(self, responder: Any, *, serves_card: bool = False) -> None:
        self.requests: list[httpx.Request] = []
        self._responder = responder
        self._serves_card = serves_card

    def __call__(self, request: httpx.Request) -> httpx.Response:
        card_path = "/a2a/.well-known/agent-card.json"
        if (
            request.url.path in {card_path, "/.well-known/agent-card.json"}
            and not self._serves_card
        ):
            return httpx.Response(404)
        self.requests.append(request)
        return self._responder(request)


def _client(
    responder: Any, *, serves_card: bool = False, **kwargs: Any
) -> tuple[AgentClient, _Recorder]:
    recorder = _Recorder(responder, serves_card=serves_card)
    client = AgentClient(base_url="http://localhost:8000", **kwargs)
    client._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(recorder),
        headers=client._http_client.headers,
    )
    return client, recorder


def _registry_digest() -> str:
    from arbora.client._generated_models import REGISTRY_DIGEST

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
def test_arbora_endpoint_refuses_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        AgentClient(base_url=url, bearer_token="caller-token")


@pytest.mark.parametrize(
    "token", ["", " ", "token\nvalue", "token\tvalue", "tok\u00e9n"]
)
@pytest.mark.spec("TUI-RUNTIME-R001.2")
def test_arbora_client_rejects_invalid_caller_credential(token: str) -> None:
    with pytest.raises(ValueError, match="invalid caller credential"):
        AgentClient(base_url="https://remote.example", bearer_token=token)


@pytest.mark.spec("TUI-RUNTIME-R001.2")
def test_remote_arbora_endpoint_requires_explicit_caller_credential() -> None:
    with pytest.raises(ValueError, match="requires caller credential"):
        AgentClient(base_url="https://remote.example")


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.2")
async def test_remote_arbora_environment_requires_operator_credential(
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

    events = [
        event
        async for event in client.stream("hello", session_id="ctx-1", model="local-only-preference")
    ]

    request = recorder.requests[0]
    sent = json.loads(request.content)
    assert request.url.path == "/a2a"
    assert request.headers["Authorization"] == "Bearer tok"
    assert request.headers["Idempotency-Key"]
    assert "local-only-preference" not in request.content.decode()
    assert sent["method"] == "message/stream"
    assert sent["params"]["message"]["contextId"] == "ctx-1"
    assert sent["params"]["message"]["parts"] == [{"kind": "text", "text": "hello"}]
    assert "metadata" not in sent["params"]["message"]
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
@pytest.mark.spec("TUI-RUNTIME-R012.5.1")
@pytest.mark.parametrize("part", [
    {"type": "image", "url": "u"},
    {"image": "encoded", "media_type": "image/png"},
    {"type": "text", "text": "caption", "image": "encoded"},
    {"file": {"bytes": "encoded"}},
    {"kind": "file", "file": {"uri": "https://example.test/a.png"}},
    {"type": "text", "text": 42},
    {},
    None,
])
async def test_non_text_parts_are_refused_before_any_request(part):
    client, recorder = _client(lambda request: httpx.Response(500))

    events = [
        event
        async for event in client.stream("x", parts=[part])
    ]

    assert events[-1]["type"] == "error"
    assert recorder.requests == []
    await client.close()



def _text_file(content: bytes = b"notes\r\n", name: str = "notes.txt") -> dict[str, Any]:
    return {
        "kind": "file",
        "file": {
            "bytes": base64.b64encode(content).decode("ascii"),
            "mimeType": "text/plain",
            "name": name,
        },
    }


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.5.2")
@pytest.mark.parametrize("streaming", [True, False])
async def test_inline_text_file_preserves_exact_payload_in_existing_transport(streaming):
    expected = _text_file("\ufeffhéllo\r\n\x00world\n".encode(), "résumé.txt")
    body = _sse(_result(_task("completed")))
    client, recorder = _client(lambda request: httpx.Response(
        200, content=body if streaming else None,
        json=None if streaming else _result(_task("completed")),
    ))
    client._streaming = streaming

    events = [event async for event in client.stream("read this", parts=[expected])]

    assert not any(event["type"] == "error" for event in events)
    assert len(recorder.requests) == 1
    sent = json.loads(recorder.requests[0].content)
    assert sent["method"] == ("message/stream" if streaming else "message/send")
    assert sent["params"]["message"]["parts"] == [
        {"kind": "text", "text": "read this"}, expected,
    ]
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.5.2")
@pytest.mark.parametrize("part", [
    {"kind": "file", "file": {"bytes": "%%%", "mimeType": "text/plain"}},
    {"kind": "file", "file": {"bytes": "YQ==\n", "mimeType": "text/plain"}},
    {"kind": "file", "file": {"bytes": "é", "mimeType": "text/plain"}},
    {"kind": "file", "file": {"bytes": "", "mimeType": "text/plain"}},
    {"kind": "file", "file": {"bytes": "YQ==", "mimeType": "image/png"}},
    {"kind": "file", "file": {"bytes": "YQ==", "mimeType": "text/plain", "uri": "https://example.test/a.txt"}},
    {"kind": "file", "file": {"uri": "https://example.test/a.txt", "mimeType": "text/plain"}},
    {"kind": "file", "file": None},
    {"kind": "file", "file": {"bytes": 42, "mimeType": "text/plain"}},
    {"kind": "file", "file": {"bytes": "YQ==", "mimeType": "text/plain", "name": 42}},
    {"kind": "file", "type": "text", "file": {"bytes": "YQ==", "mimeType": "text/plain"}},
    _text_file(b"\xff"),
    _text_file(b"a", "a" * 257),
    _text_file(b"a" * 65537),
])
async def test_invalid_inline_text_file_makes_zero_requests(part):
    client, recorder = _client(lambda request: httpx.Response(500), serves_card=True)

    events = [event async for event in client.stream("read", parts=[part])]

    assert events[-1]["type"] == "error"
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.5.2")
@pytest.mark.parametrize("query,parts", [
    ("read", [_text_file()] * 9),
    ("read", [_text_file(b"a" * 32769)] * 2),
    ("a" * 65537, [_text_file()]),
    ("a" * 65536, [_text_file(b"b" * 34464)]),
    ("read", [{"text": "a"}] * 31 + [_text_file()]),
])
async def test_inline_text_message_bounds_make_zero_requests(query, parts):
    client, recorder = _client(lambda request: httpx.Response(500), serves_card=True)

    events = [event async for event in client.stream(query, parts=parts)]

    assert events[-1]["type"] == "error"
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.5.2")
@pytest.mark.parametrize("query,parts", [
    ("read", [_text_file("é".encode() * 4096)] * 8),
    ("a" * 65536, [_text_file(b"b" * 34463)]),
    ("read", [{"text": "a"}] * 30 + [_text_file()]),
])
async def test_inline_text_message_inclusive_bounds_are_admitted(query, parts):
    client, recorder = _client(lambda request: httpx.Response(
        200, content=_sse(_result(_task("completed"))),
    ))

    events = [event async for event in client.stream(query, parts=parts)]

    assert not any(event["type"] == "error" for event in events)
    assert len(recorder.requests) == 1
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.5.2")
async def test_server_upload_refusal_is_not_downgraded_or_retried():
    client, recorder = _client(lambda request: httpx.Response(400, json={
        "jsonrpc": "2.0", "id": 1,
        "error": {"code": -32602, "message": "attachments exceed configured upload size"},
    }))

    events = [event async for event in client.stream("read", parts=[_text_file()])]

    assert events[-1]["type"] == "error"
    assert events[-1]["message"] == "attachments exceed configured upload size"
    assert len(recorder.requests) == 1
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.5.1")
async def test_image_command_refusal_preserves_next_text_submission(monkeypatch):
    from unittest.mock import MagicMock

    from agent_terminal_ui.app import AgentApp
    from agent_terminal_ui.commands import CommandProcessor

    task = _task("completed")
    client, recorder = _client(
        lambda request: httpx.Response(200, content=_sse(_result(task)))
    )
    app = AgentApp(client=client)
    notice = MagicMock()
    monkeypatch.setattr(app, "notify", notice)
    app._pending_parts = [{"text": "existing text attachment"}]
    reader = MagicMock(side_effect=AssertionError("must not read an image"))
    monkeypatch.setattr(Path, "read_bytes", reader)

    assert await CommandProcessor(app).process('/image "image.png"')

    assert recorder.requests == []
    reader.assert_not_called()
    notice.assert_called_once_with(
        "Images are not supported by the current Arbora transport.", severity="warning"
    )
    assert app._pending_parts == [{"text": "existing text attachment"}]
    parts = app._collect_pending_parts("next prompt")
    events = [event async for event in client.stream("next prompt", parts=parts)]
    assert not any(event["type"] == "error" for event in events)
    sent = json.loads(recorder.requests[0].content)
    sent_parts = sent["params"]["message"]["parts"]
    assert {"kind": "text", "text": "existing text attachment"} in sent_parts
    assert {"kind": "text", "text": "next prompt"} in sent_parts
    assert all(part["kind"] == "text" for part in sent_parts)
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
    with pytest.raises(ArboraOperationError) as caught:
        await client.invoke_op("query.uql", {"text": "RETURN 1", "params": {}})
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
    assert await client.invoke_op("query.uql", {"text": "RETURN 1", "params": {}}) == {
        "rows": [1]
    }
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
    with pytest.raises(ArboraOperationError) as caught:
        await client.invoke_op("query.uql", {})
    assert caught.value.code == "REGISTRY_MISMATCH"
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.1")
async def test_versioned_operation_rejects_unregistered_op_before_network() -> None:
    client, recorder = _client(lambda _request: httpx.Response(500))
    with pytest.raises(ArboraOperationError) as caught:
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
    with pytest.raises(ArboraOperationError) as caught:
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
    import arbora.client._generated_models as models

    def missing_registry(_op: str) -> None:
        raise FileNotFoundError("registry.json")

    monkeypatch.setattr(models, "schema_for", missing_registry)
    client, recorder = _client(lambda _request: httpx.Response(500))
    with pytest.raises(ArboraOperationError) as caught:
        await client.invoke_op("query.uql", {})
    assert caught.value.code == "CLIENT_UNAVAILABLE"
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("op", ["approvals.grant", "Approvals.Deny"])
async def test_approval_operation_is_refused_before_network(op: str):
    client, recorder = _client(lambda _request: httpx.Response(500))
    with pytest.raises(ArboraOperationError) as caught:
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
    with pytest.raises(ArboraOperationError) as caught:
        await client.invoke_op("query.uql", {"text": "RETURN 1", "params": {}})
    assert caught.value.code == "INVALID_ENVELOPE"
    await client.close()


@pytest.mark.asyncio
async def test_bearer_credential_cannot_replace_signed_plan_binding():
    client, recorder = _client(
        lambda _request: httpx.Response(500), bearer_token="caller-token"
    )
    with pytest.raises(ArboraOperationError) as caught:
        await client.confirm_plan(
            plan_ref="p1", op="query.uql", params={"query": "MATCH ()"}
        )
    assert caught.value.code == "APPROVAL_UNAVAILABLE"
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
async def test_unsigned_plan_confirmation_refuses_before_network():
    client, recorder = _client(lambda _request: httpx.Response(500))
    with pytest.raises(ArboraOperationError) as caught:
        await client.confirm_plan(
            plan_ref="p1", op="query.uql", params={"query": "MATCH ()"}
        )
    assert caught.value.code == "CALLER_CREDENTIAL_REQUIRED"
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.5")
@pytest.mark.parametrize(
    ("token", "refusal"),
    [(None, "CALLER_CREDENTIAL_REQUIRED"), ("caller-token", "APPROVAL_UNAVAILABLE")],
)
async def test_unsigned_input_required_decision_cannot_resume_a2a_task(token, refusal):
    client, recorder = _client(lambda _request: httpx.Response(500), bearer_token=token)
    client._pending_plans[_TASK] = {
        "plan_ref": "p1",
        "op": "query.uql",
        "params": {"query": "MATCH ()"},
    }
    events = [event async for event in client.send_decision({_TASK: "accept"})]
    assert events[-1]["type"] == "error"
    assert events[-1]["message"] == refusal
    assert _TASK in client._pending_plans
    assert recorder.requests == []
    await client.close()


@pytest.mark.asyncio
async def test_confirm_plan_refuses_approval_operation_without_network():
    client, recorder = _client(lambda _request: httpx.Response(500))
    with pytest.raises(ArboraOperationError) as caught:
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
            "arboraPlan": {
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
            "arboraPlan": {
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
            "arboraPlan": {
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
    card = {"name": "Arbora", "capabilities": {"streaming": True}}
    client, recorder = _client(
        lambda request: httpx.Response(200, json=card), serves_card=True
    )

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
    dependency of this client — conversation turns use Arbora's A2A
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


@pytest.mark.asyncio
async def test_legacy_fleet_grant_is_refused_before_network():
    client, recorder = _client(lambda _request: httpx.Response(500))
    with pytest.raises(ArboraOperationError) as caught:
        await client.grant_fleet_approval("job-1")
    assert caught.value.code == "APPROVAL_UNAVAILABLE"
    assert recorder.requests == []
    await client.close()


def test_remote_cleartext_endpoint_requires_tls() -> None:
    with pytest.raises(ValueError, match="remote Arbora endpoint requires TLS"):
        AgentClient("http://agent.test")


def _unary_server(states: list[str], *, card: dict[str, Any] | None = None) -> Any:
    """An A2A server without ``message/stream``, like Arbora's served agent."""
    pending = list(states)

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200, json=card or {"capabilities": {"streaming": False}}
            )
        method = json.loads(request.content)["method"]
        if method == "message/stream":
            return httpx.Response(500, text="Internal Server Error")
        task = _task(pending.pop(0))
        if task["status"]["state"] == "completed":
            task["artifacts"] = [{"parts": [{"kind": "text", "text": "the answer"}]}]
        return httpx.Response(200, json=_result(task))

    return respond


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R002")
async def test_stream_polls_a_unary_task_when_the_card_refuses_streaming():
    recorder = _Recorder(
        _unary_server(["submitted", "working", "completed"]), serves_card=True
    )
    client = AgentClient(base_url="http://localhost:8000", bearer_token="tok")
    client.poll_interval = 0
    client._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(recorder), headers=client._http_client.headers
    )

    events = [event async for event in client.stream("hello", session_id="ctx-1")]

    calls = [
        json.loads(r.content)["method"] for r in recorder.requests if r.method == "POST"
    ]
    assert calls == ["message/send", "tasks/get", "tasks/get"]
    sent = json.loads(recorder.requests[1].content)["params"]["message"]
    assert sent["kind"] == "message"
    assert sent["contextId"] == "ctx-1"
    assert recorder.requests[1].headers["Idempotency-Key"]
    assert [e["type"] for e in events] == [
        "session_started",
        "sideband",
        "sideband",
        "text",
        "sideband",
        "turn_end",
    ]
    assert events[3]["content"] == "the answer"
    assert client.current_task_id == _TASK


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R002")
async def test_unary_task_failure_reports_an_error_and_ends_the_turn():
    recorder = _Recorder(_unary_server(["submitted", "failed"]), serves_card=True)
    client = AgentClient(base_url="http://localhost:8000")
    client.poll_interval = 0
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))

    events = [event async for event in client.stream("hello")]

    assert [e["type"] for e in events][-2:] == ["error", "turn_end"]
    assert not any(e["type"] == "text" for e in events)


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.1.1")
@pytest.mark.parametrize("terminal", ["completed", "failed", "canceled"])
async def test_nonblocking_turn_binds_task_and_never_replays(terminal):
    recorder = _Recorder(
        _unary_server(["submitted", "working", terminal]), serves_card=True
    )
    client = AgentClient(base_url="http://localhost:8000")
    client.poll_interval = 0
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    events = [event async for event in client.stream("hello")]
    requests = [json.loads(r.content) for r in recorder.requests if r.method == "POST"]
    assert requests[0]["params"]["configuration"] == {"blocking": False}
    assert [r["method"] for r in requests] == ["message/send", "tasks/get", "tasks/get"]
    assert all(r["params"] == {"id": _TASK} for r in requests[1:])
    assert events[-1]["type"] == "turn_end"
    assert events[-1]["state"] == terminal
    await client._http_client.aclose()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.1.1")
@pytest.mark.parametrize("fault", ["id", "contextId", "runId", "denied", "timeout"])
async def test_nonblocking_poll_refuses_bad_identity_and_unknown_outcomes(fault):
    calls = []

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        task = _task("submitted" if body["method"] == "message/send" else "completed")
        if body["method"] == "tasks/get":
            if fault == "denied":
                return httpx.Response(403, json=_result(task))
            if fault == "runId":
                task["metadata"]["arbora"]["runId"] = "foreign"
            elif fault in {"id", "contextId"}:
                task[fault] = "foreign"
        return httpx.Response(200, json=_result(task))

    client = AgentClient(base_url="http://localhost:8000")
    client._streaming = False
    client.poll_interval = 0
    if fault == "timeout":
        client.poll_timeout = 0
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    events = [event async for event in client.stream("hello")]
    assert events[-1]["type"] == "error"
    assert not any(event["type"] in {"text", "turn_end"} for event in events)
    assert sum(call["method"] == "message/send" for call in calls) == 1
    assert client.current_task_id == _TASK
    await client._http_client.aclose()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.1.1")
async def test_nonblocking_pending_turn_can_cancel_returned_task():
    calls = []

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(
            200,
            json=_result(
                _task("canceled" if body["method"] == "tasks/cancel" else "working")
            ),
        )

    client = AgentClient(base_url="http://localhost:8000")
    client._streaming = False
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    stream = client.stream("hello")
    await anext(stream)
    pending = await anext(stream)
    assert pending["data"]["state"] == "working"
    canceled = await client.cancel_task()
    assert canceled["status"]["state"] == "canceled"
    assert calls[-1]["params"] == {"id": _TASK}
    await stream.aclose()
    assert [call["method"] for call in calls] == ["message/send", "tasks/cancel"]
    await client._http_client.aclose()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.1.1")
@pytest.mark.parametrize("outcome", ["empty", "unknown"])
async def test_nonblocking_submission_never_invents_reply_or_replays(outcome):
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        if outcome == "unknown":
            raise httpx.ReadTimeout("Submission outcome unknown", request=request)
        return httpx.Response(200, json=_result(_task("completed")))

    client = AgentClient(base_url="http://localhost:8000")
    client._streaming = False
    client._current_task_id = "old-task"
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    events = [event async for event in client.stream("hello")]
    assert len(calls) == 1
    assert not any(event["type"] == "text" for event in events)
    if outcome == "unknown":
        assert events[-1]["type"] == "error"
        assert client.current_task_id is None
    else:
        assert events[-1]["type"] == "turn_end"
    await client._http_client.aclose()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.1.1")
@pytest.mark.parametrize("fault", ["context", "runId", "emptyRunId"])
async def test_nonblocking_initial_correlation_refuses_before_binding(fault):
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        task = _task("working")
        if fault == "context":
            task["contextId"] = "a2a-context-" + "f" * 64
        else:
            task["metadata"]["arbora"]["runId"] = {} if fault == "runId" else ""
        return httpx.Response(200, json=_result(task))

    client = AgentClient(base_url="http://localhost:8000")
    client._streaming = False
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    events = [event async for event in client.stream("hello", session_id=_CONTEXT)]
    assert [event["type"] for event in events] == ["session_started", "error"]
    assert client.current_task_id is None
    with pytest.raises(ValueError, match="no A2A task"):
        await client.cancel_task()
    assert len(calls) == 1
    await client._http_client.aclose()
