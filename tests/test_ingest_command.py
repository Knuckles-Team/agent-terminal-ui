"""Tests for the /ingest fact-extraction command + client methods (ECO-4.43)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agent_terminal_ui.client import AgentClient
from agent_terminal_ui.commands import CommandProcessor


@pytest.fixture
def client() -> AgentClient:
    return AgentClient(base_url="http://localhost:8000")


def _resp(payload, status=200, text=""):
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.json.return_value = payload
    r.text = text
    r.raise_for_status = MagicMock(return_value=None)
    return r


@pytest.mark.asyncio
async def test_submit_extraction_posts(client: AgentClient) -> None:
    with patch.object(client._http_client, "post", new_callable=AsyncMock) as post:
        post.return_value = _resp({"status": "submitted", "job_id": "j1"})
        out = await client.submit_extraction(text="hello", rounds=2)
    assert out["job_id"] == "j1"
    args, kwargs = post.call_args
    assert args[0].endswith("/api/enhanced/extract/submit")
    assert kwargs["json"]["rounds"] == 2


@pytest.mark.asyncio
async def test_extraction_jsonl_returns_text(client: AgentClient) -> None:
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as get:
        get.return_value = _resp(None, text='{"subject":"A"}\n')
        out = await client.extraction_jsonl("j1")
    assert "subject" in out


def _fake_app(client):
    app = MagicMock()
    conv = MagicMock()
    conv.add_info = AsyncMock()
    app.query_one = MagicMock(return_value=conv)
    app.agent_client = client
    app.notify = MagicMock()
    return app, conv


@pytest.mark.asyncio
async def test_cmd_ingest_streams_facts() -> None:
    client = MagicMock()
    client.submit_extraction = AsyncMock(
        return_value={"status": "submitted", "job_id": "j1"}
    )

    async def _stream(job_id):
        yield {"type": "round_start", "round": 1}
        yield {
            "type": "fact",
            "is_duplicate": False,
            "fact": {
                "subject": "Jina AI",
                "predicate": "built",
                "object": "v5",
                "confidence": 90,
                "tags": ["ai"],
            },
        }
        yield {"type": "fact", "is_duplicate": True, "fact": {"subject": "x"}}
        yield {"type": "job_done", "state": "done"}

    client.stream_extraction = _stream
    app, conv = _fake_app(client)
    handler = CommandProcessor(app)
    await handler.cmd_ingest("-- some document text")

    client.submit_extraction.assert_awaited_once()
    rendered = " ".join(str(c.args[0]) for c in conv.add_info.await_args_list)
    assert "Jina AI" in rendered
    assert "1 facts" in rendered  # one kept, one duplicate suppressed
    assert "duplicates suppressed" in rendered


@pytest.mark.asyncio
async def test_cmd_ingest_handles_cold_engine() -> None:
    client = MagicMock()
    client.submit_extraction = AsyncMock(
        return_value={"status": "unavailable", "message": "engine cold"}
    )
    app, conv = _fake_app(client)
    handler = CommandProcessor(app)
    await handler.cmd_ingest("https://example.com")
    rendered = " ".join(str(c.args[0]) for c in conv.add_info.await_args_list)
    assert "unavailable" in rendered.lower()
