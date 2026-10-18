"""Public generated-client fixtures, not live native service qualification."""
import json
from unittest.mock import MagicMock

import httpx
import pytest
from arbora.client._generated_models import REGISTRY_DIGEST
from textual.app import App
from textual.widgets import Static

from agent_terminal_ui.client import AgentClient, ArboraOperationError
from agent_terminal_ui.commands import CommandProcessor
from agent_terminal_ui.screens.usage import UsageScreen

pytestmark = [pytest.mark.asyncio, pytest.mark.spec("TUI-RUNTIME-R012.4.2")]


@pytest.fixture
def client_factory():
    def make(values):
        requests = []
        def reply(request):
            requests.append(request)
            value = values.pop(0)
            envelope = {"meta": {"registry_digest": REGISTRY_DIGEST}}
            if isinstance(value, str):
                envelope.update(ok=False, error={"code": value})
            else:
                envelope.update(ok=True, result={"value": value})
            return httpx.Response(200, json=envelope)
        client = AgentClient(base_url="http://localhost:8000")
        client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
        return client, requests
    return make


async def test_catalog_follows_opaque_cursor(client_factory):
    item = {"id": "tool:one", "name": "one", "description": "first", "server": "s"}
    client, requests = client_factory([{"items": [item], "next_cursor": "opaque"}, {"items": [], "next_cursor": None}])
    assert await client.list_tools_only() == [item]
    assert [r.url.path for r in requests] == ["/api/v1/ops/fleet.catalog.list"] * 2
    assert json.loads(requests[1].content)["cursor"] == "opaque"
    assert json.loads(requests[0].content)["kinds"] == ["tool"]
    await client._http_client.aclose()


@pytest.mark.parametrize("values,code", [
    (["UNAVAILABLE"], "UNAVAILABLE"),
    ([{"items": [] , "next_cursor": "x"}] * 2, "INVALID_ENVELOPE"),
    ([{"items": "bad"}], "INVALID_ENVELOPE"),
    ([{"items": []}], "INVALID_ENVELOPE"),
    ([{"items": [], "next_cursor": str(i)} for i in range(10)], "CATALOG_PAGE_LIMIT"),
])
async def test_catalog_never_returns_partial_or_false_empty(client_factory, values, code):
    client, _ = client_factory(values)
    with pytest.raises(ArboraOperationError, match=code):
        await client.list_mcp_tools()
    await client._http_client.aclose()


async def test_status_and_usage_use_served_operations(client_factory):
    client, requests = client_factory([{"children": {"s": {}}}, {"totals": {"tokens": 2}}])
    assert await client.get_mcp_config() == {"children": {"s": {}}}
    assert await client.get_usage_summary() == {"totals": {"tokens": 2}}
    assert [r.url.path for r in requests] == ["/api/v1/ops/fleet.status", "/api/v1/ops/usage.read"]
    await client._http_client.aclose()


async def test_commands_refuse_mutations_without_transport(client_factory):
    client, requests = client_factory([])
    app = MagicMock()
    app._client = client
    processor = CommandProcessor(app)
    await processor.cmd_tools_only("toggle one")
    await processor.cmd_mcp_reload("")
    assert app.notify.call_count == 2
    assert requests == []
    await client._http_client.aclose()


async def test_usage_clears_previous_metrics_on_refusal(client_factory):
    client, requests = client_factory([{"totals": {"tokens": 42}}, "UNAVAILABLE", {"totals": {}}])
    class UsageApp(App):
        agent_client = client
        def on_mount(self):
            self.push_screen(UsageScreen())
    app = UsageApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.screen.query_one("#usage-hist", Static)
        assert "tokens: 42" in str(widget.render())
        await app.screen.refresh_usage().wait()
        assert "unavailable" in str(widget.render())
        assert "42" not in str(widget.render())
        await app.screen.refresh_usage().wait()
        assert "totals unavailable" in str(widget.render())
    assert len(requests) == 3
    await client._http_client.aclose()
