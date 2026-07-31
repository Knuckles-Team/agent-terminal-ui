from unittest.mock import AsyncMock, patch

import pytest

from agent_terminal_ui.client import AgentClient


@pytest.fixture
def run_client():
    client = AgentClient()
    return client


@pytest.mark.asyncio
async def test_create_session(run_client):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.raise_for_status = lambda: None
        mock_response.json.return_value = {"session_id": "test_123"}
        mock_post.return_value = mock_response

        session_id = await run_client.create_session()
        assert session_id == "test_123"


@pytest.mark.asyncio
async def test_stream_mode_injection(run_client):
    with (
        patch.object(run_client, "create_session", return_value="sess_1"),
        patch.object(run_client, "send_rpc", new_callable=AsyncMock) as mock_rpc,
        patch.object(run_client, "stream_events") as mock_stream,
    ):
        # Make stream return empty
        async def empty_gen(*args, **kwargs):
            for _ in []:
                yield

        mock_stream.side_effect = empty_gen

        async for _ in run_client.stream("/plan list files"):
            pass

        mock_rpc.assert_called_with(
            "sess_1",
            "message/send",
            {"content": "list files", "modeId": "plan", "parts": []},
        )


@pytest.mark.asyncio
async def test_stream_propagates_session_identity_and_normalizes_deltas(run_client):
    """Every event should identify one session and use the shared delta name."""

    async def raw_events(_session_id):
        yield {"type": "text-delta", "delta": "hel"}
        yield {"type": "text-delta", "text": "lo"}
        yield {"type": "turn-end", "usage": {"total_tokens": 3}}

    with (
        patch.object(run_client, "create_session", return_value="sess-stream"),
        patch.object(run_client, "send_rpc", new_callable=AsyncMock),
        patch.object(run_client, "stream_events", side_effect=raw_events),
    ):
        events = [event async for event in run_client.stream("hello")]

    assert events[0] == {
        "type": "session_started",
        "session_id": "sess-stream",
    }
    assert [event["type"] for event in events[1:3]] == [
        "text_delta",
        "text_delta",
    ]
    assert [event["content"] for event in events[1:3]] == ["hel", "lo"]
    assert all(event["session_id"] == "sess-stream" for event in events)
    assert run_client.current_session_id == "sess-stream"


@pytest.mark.asyncio
async def test_send_decision_reuses_session_and_normalizes_resume_stream(run_client):
    """Approval resumes should stay on the active session and event contract."""

    async def resumed_events(_session_id):
        yield {"type": "text-delta", "delta": "resumed"}
        yield {"type": "turn-end"}

    run_client._current_session_id = "sess-approval"
    with (
        patch.object(run_client, "send_rpc", new_callable=AsyncMock) as mock_rpc,
        patch.object(run_client, "stream_events", side_effect=resumed_events),
    ):
        events = [
            event
            async for event in run_client.send_decision(
                {"call-1": "accept"}, feedback="continue"
            )
        ]

    mock_rpc.assert_awaited_once_with(
        "sess-approval",
        "approve_tool",
        {
            "call_id": "call-1",
            "decision": "accept",
            "feedback": "continue",
        },
    )
    assert events[0] == {
        "type": "text_delta",
        "content": "resumed",
        "session_id": "sess-approval",
    }
    assert events[1] == {"type": "turn_end", "session_id": "sess-approval"}


# ── D-FE-2 regression coverage ──────────────────────────────────────────
#
# (a) ``agent-client-protocol`` (Zed's real ACP SDK) is not a dependency of
#     this package: nothing in ``agent_terminal_ui`` imports
#     ``agent_client_protocol``, and ``AgentClient`` must construct and work
#     even when that package is not importable/installed at all.
# (b) ``ACP_URL`` is now actually read (see ``AgentApp.__init__`` in
#     ``app.py``) rather than being a documented-but-dead env var; at the
#     client level this is exercised via the ``acp_url`` constructor kwarg.


def test_agent_client_protocol_module_is_not_imported_by_this_package():
    """``agent_client_protocol`` (the real Zed ACP SDK) must not be a runtime
    dependency of this client — this repo speaks its own hand-rolled
    JSON-RPC/SSE convention, not that SDK's wire format."""
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
    assert client.acp_url == "http://localhost:8000/acp"


def test_acp_url_override_replaces_derived_default():
    """D-FE-2(b): passing ``acp_url`` overrides the ``{base_url}/acp`` default."""
    client = AgentClient(
        base_url="http://localhost:8000", acp_url="http://otherhost:9001/acp"
    )
    assert client.acp_url == "http://otherhost:9001/acp"


def test_acp_url_defaults_when_not_provided():
    client = AgentClient(base_url="http://localhost:8000")
    assert client.acp_url == "http://localhost:8000/acp"
