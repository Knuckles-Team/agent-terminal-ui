"""Card discovery never treats an authorization refusal as a fallback route."""

import json

import httpx
import pytest

from agent_terminal_ui.client import AgentClient

pytestmark = pytest.mark.spec("TUI-RUNTIME-R002.1.6")
ROOT = "/.well-known/agent-card.json"
SCOPED = "/a2a/.well-known/agent-card.json"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 404, 405, 401, 403, 500])
async def test_discovery_falls_back_only_when_root_is_absent(status):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            status if request.url.path == ROOT else 200,
            json={"name": "unary", "capabilities": {"streaming": False}},
        )

    client = AgentClient("http://localhost:8000", bearer_token="fixture-token")
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        headers={"Authorization": "Bearer fixture-token"},
    )
    try:
        assert await client.streaming_supported() is (status not in {200, 404, 405})
        assert [r.url.path for r in requests] == (
            [ROOT, SCOPED] if status in {404, 405} else [ROOT]
        )
        assert all(
            r.headers["authorization"] == "Bearer fixture-token" for r in requests
        )
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"not json", b"[]"])
async def test_malformed_root_card_does_not_probe_scoped_path(body):
    paths = []

    def respond(request):
        paths.append(request.url.path)
        return httpx.Response(200, content=body)

    client = AgentClient("http://localhost:8000")
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        assert await client.get_metadata() == {}
        assert paths == [ROOT]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_root_unary_card_sends_once_and_renders_history():
    methods = []

    def respond(request):
        if request.method == "GET":
            assert request.url.path == ROOT
            return httpx.Response(200, json={"capabilities": {"streaming": False}})
        methods.append(json.loads(request.content)["method"])
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "message/send",
                "result": {
                    "id": "fixture-task",
                    "contextId": "a2a-context-" + "1" * 64,
                    "metadata": {"arbora": {"runId": "fixture-task"}},
                    "kind": "task",
                    "status": {"state": "completed"},
                    "history": [
                        {
                            "kind": "message",
                            "role": "agent",
                            "parts": [{"kind": "text", "text": "hello back"}],
                        }
                    ],
                },
            },
        )

    client = AgentClient("http://localhost:8000")
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        events = [event async for event in client.stream("hello")]
        assert methods == ["message/send"]
        assert [e["content"] for e in events if e["type"] == "text"] == ["hello back"]
        assert events[-1]["type"] == "turn_end"
    finally:
        await client.close()
