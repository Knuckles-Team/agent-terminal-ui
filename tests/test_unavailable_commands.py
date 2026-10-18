"""Unserved management commands never reach retired REST routes."""

from unittest.mock import MagicMock

import httpx
import pytest

from agent_terminal_ui.client import AgentClient
from agent_terminal_ui.commands import CommandProcessor


@pytest.mark.spec("TUI-RUNTIME-R012.4.1")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "arguments", "operation"),
    [
        ("skills", "", "skills.list"),
        ("skills", "toggle example", "skills.list"),
        ("prompts", "", "prompts.list"),
        ("prompts", "list", "prompts.list"),
        ("prompts", "get example", "prompts.list"),
        ("prompts", "set example content", "prompts.list"),
        ("prompts", "versions example", "prompts.list"),
        ("prompts", "rollback example version", "prompts.list"),
        ("prompts", "add example content", "prompts.list"),
        ("kb", "", "kb.list"),
        ("kb", "list", "kb.list"),
        ("kb", "search query", "kb.list"),
        ("kb", "article example", "kb.list"),
        ("kb", "ingest source target", "kb.list"),
        ("cron", "", "cron.calendar"),
        ("cron", "calendar", "cron.calendar"),
        ("cron", "logs 5", "cron.calendar"),
        ("pipeline", "", "pipeline.status"),
        ("pipeline", "status", "pipeline.status"),
        ("pipeline", "run ingest", "pipeline.status"),
    ],
)
async def test_unavailable_command_makes_no_request(
    command: str, arguments: str, operation: str
) -> None:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(404)

    client = AgentClient()
    await client._http_client.aclose()
    async with httpx.AsyncClient(transport=httpx.MockTransport(record)) as transport:
        client._http_client = transport
        app = MagicMock()
        app._client = client
        processor = CommandProcessor(app)

        assert await processor.process(f"/{command} {arguments}")

        app.notify.assert_called_once_with(
            f"/{command} unavailable: Arbora does not serve {operation} "
            "or its management operations.",
            severity="warning",
        )
        app.query_one.assert_not_called()
        app.push_screen.assert_not_called()
        assert requests == []
