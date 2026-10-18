"""Read-only CLI observation over the existing authenticated A2A transport."""

import asyncio
import io
import json
import sys
from typing import Any

import httpx
import pytest

from agent_terminal_ui import headless
from agent_terminal_ui.client import AgentClient
from agent_terminal_ui.headless import StreamSink, observe_task
from agent_terminal_ui.terminal_ui import terminal_ui


def task(state: str = "completed", **changes: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": "t1", "contextId": "c1", "status": {"state": state},
        "metadata": {"arbora": {"runId": "r1"}},
        "artifacts": [{"parts": [{"kind": "text", "text": "answer"}]}],
    }
    value.update(changes)
    return value


def client_with_responses(responses: list[dict[str, Any]], seen: list[Any]) -> AgentClient:
    client = AgentClient(base_url="https://test.invalid", bearer_token="fixture-token")
    client.poll_interval = 0

    def reply(request: httpx.Request) -> httpx.Response:
        seen.append((json.loads(request.content), request.headers.get("authorization")))
        return httpx.Response(200, json=responses.pop(0))

    client._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(reply), headers={"Authorization": "Bearer fixture-token"}
    )
    return client


def test_cli_observes_existing_task_without_effects(monkeypatch, capsys):
    seen: list[Any] = []
    client = client_with_responses([
        {"result": task("working")}, {"result": task()},
    ], seen)
    monkeypatch.setattr(headless, "client_from_environment", lambda: client)
    monkeypatch.setattr(sys, "argv", ["agent-terminal-ui", "--observe-task", "t1"])
    terminal_ui()
    text = capsys.readouterr().out
    assert "task: t1 | context: c1 | run: r1" in text
    assert "state: working" in text and "state: completed" in text
    assert "answer" in text
    assert len(seen) == 2
    assert all(body["method"] == "tasks/get" and body["params"] == {"id": "t1"}
               and auth == "Bearer fixture-token" for body, auth in seen)
    assert client._http_client.is_closed


@pytest.mark.parametrize("extra", [
    ["--prompt", "x"], ["--override"], ["--bg"], ["--model", "m"],
    ["--session", "c"], ["--mode", "build"],
])
def test_cli_refuses_effect_options_before_client(monkeypatch, extra):
    def forbidden():
        raise AssertionError("invalid options constructed a client")
    monkeypatch.setattr(headless, "client_from_environment", forbidden)
    monkeypatch.setattr(sys, "argv", ["tui", "--observe-task", "t1", *extra])
    with pytest.raises(SystemExit) as exc:
        terminal_ui()
    assert exc.value.code == 2


@pytest.mark.parametrize("changes", [
    {"id": "other"}, {"contextId": "other"},
    {"metadata": {"arbora": {"runId": "other"}}},
    {"status": {"state": "invented"}},
    {"artifacts": [{"parts": [{"kind": "file", "text": "secret"}]}]},
])
async def test_changed_or_malformed_reads_stop_without_output(changes):
    seen: list[Any] = []
    client = client_with_responses([
        {"result": task("working")}, {"result": task(**changes)},
    ], seen)
    out = io.StringIO()
    try:
        assert not await observe_task(client, "t1", StreamSink(out))
        assert len(seen) == 2
        assert "Task unavailable" in out.getvalue()
        assert "answer" not in out.getvalue() and "secret" not in out.getvalue()
    finally:
        await client.aclose()


async def test_denial_after_success_does_not_retry():
    seen: list[Any] = []
    client = client_with_responses([
        {"result": task("working")}, {"error": {"code": -32001, "message": "secret"}},
    ], seen)
    out = io.StringIO()
    try:
        assert not await observe_task(client, "t1", StreamSink(out))
        assert len(seen) == 2 and "secret" not in out.getvalue()
    finally:
        await client.aclose()


@pytest.mark.parametrize("state", ["input-required", "canceled", "failed", "completed"])
async def test_missing_output_stays_unavailable_and_never_approves(state):
    seen: list[Any] = []
    client = client_with_responses([{"result": task(state, artifacts=None)}], seen)
    out = io.StringIO()
    try:
        await observe_task(client, "t1", StreamSink(out))
        assert "output: unavailable" in out.getvalue()
        assert len(seen) == 1 and seen[0][0]["method"] == "tasks/get"
        if state == "input-required":
            assert "approval or input remains required" in out.getvalue()
    finally:
        await client.aclose()


async def test_missing_later_run_retains_original_binding():
    seen: list[Any] = []
    client = client_with_responses([
        {"result": task("working")}, {"result": task(metadata={})},
    ], seen)
    out = io.StringIO()
    try:
        assert await observe_task(client, "t1", StreamSink(out))
        assert out.getvalue().count("run: r1") == 2
    finally:
        await client.aclose()


async def test_local_cancellation_closes_client_without_remote_cancel(monkeypatch):
    started = asyncio.Event()
    client = AgentClient(base_url="https://test.invalid", bearer_token="fixture-token")
    seen: list[str] = []

    async def reply(request):
        seen.append(json.loads(request.content)["method"])
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("cancelled request continued")

    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
    monkeypatch.setattr(headless, "client_from_environment", lambda: client)
    pending = asyncio.create_task(headless.run_task_observer("t1"))
    await started.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert client._http_client.is_closed and seen == ["tasks/get"]


async def test_terminal_control_sequences_are_not_emitted():
    seen: list[Any] = []
    client = client_with_responses([{"result": task(artifacts=[{
        "parts": [{"kind": "text", "text": "safe\x1b]52;c;secret\x07\r\x85\nline"}]
    }])}], seen)
    out = io.StringIO()
    try:
        assert await observe_task(client, "t1", StreamSink(out))
        assert all(c not in out.getvalue() for c in ("\x1b", "\x07", "\r", "\x85"))
        assert "safe" in out.getvalue()
    finally:
        await client.aclose()


@pytest.mark.parametrize("task_id", ["", " ", "x" * 513, "bad\x1bname", "bad\nname"])
async def test_invalid_task_identity_makes_zero_requests(task_id):
    seen: list[Any] = []
    client = client_with_responses([], seen)
    try:
        assert not await observe_task(client, task_id, StreamSink(io.StringIO()))
        assert seen == []
    finally:
        await client.aclose()


@pytest.mark.parametrize("changes", [
    {"contextId": "bad\nforged"},
    {"metadata": {"arbora": {"runId": "bad\x1b]52;"}}},
])
async def test_remote_identity_controls_refuse_before_render(changes):
    seen: list[Any] = []
    client = client_with_responses([{"result": task(**changes)}], seen)
    out = io.StringIO()
    try:
        assert not await observe_task(client, "t1", StreamSink(out))
        assert "forged" not in out.getvalue() and "\x1b" not in out.getvalue()
        assert "task: t1" not in out.getvalue()
    finally:
        await client.aclose()
