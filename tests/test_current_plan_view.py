"""Current-plan consumer evidence, not production harness activation."""
import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import httpx
import pytest
from arbora.client._generated_models import REGISTRY_DIGEST
from textual.app import App
from textual.widgets import Static

from agent_terminal_ui.client import AgentClient
from agent_terminal_ui.commands import CommandProcessor
from agent_terminal_ui.tui.run_inspector import CurrentPlanScreen, current_plan_display

pytestmark = pytest.mark.spec("TUI-RUNTIME-R010.4.1")


def snapshot():
    now = datetime.now(UTC)
    return {"availability": "available", "snapshot": {
        "run_id": "run-1", "revision": 2,
        "observed_at": (now - timedelta(seconds=1)).isoformat(),
        "expires_at": (now + timedelta(seconds=30)).isoformat(),
        "items": [{"text": "[red]literal[/red]", "status": "in_progress"}],
    }}


def test_current_plan_preserves_order_and_empty_availability():
    value = snapshot()
    text, ttl = current_plan_display(value, "run-1", datetime.now(UTC))
    assert "in_progress: [red]literal[/red]" in text and ttl > 0
    value["snapshot"]["items"] = []
    assert "available and empty" in current_plan_display(value, "run-1", datetime.now(UTC))[0]
    assert current_plan_display({"availability": "unavailable"}, "run-1", datetime.now(UTC))[1] == 0


@pytest.mark.parametrize("field,value", [
    ("run_id", "other"), ("revision", True), ("revision", -1),
    ("observed_at", "2999-01-01T00:00:00Z"),
    ("expires_at", "2000-01-01T00:00:00Z"),
    ("expires_at", "2999-01-01T00:00:00+01:00"),
    ("items", [{"text": "secret", "status": "unknown"}]),
    ("items", [{"text": "x", "status": "done"}] * 101),
])
def test_invalid_plan_is_never_rendered(field, value):
    raw = snapshot()
    raw["snapshot"][field] = value
    with pytest.raises(ValueError):
        current_plan_display(raw, "run-1", datetime.now(UTC))


@pytest.mark.asyncio
async def test_generated_client_sends_only_explicit_run():
    requests = []
    def reply(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "meta": {"registry_digest": REGISTRY_DIGEST}, "result": {"value": snapshot()}})
    client = AgentClient(base_url="http://localhost")
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
    result = await client.get_current_plan("run-1")
    assert result["snapshot"]["run_id"] == "run-1"
    assert requests[0].url.path == "/api/v1/ops/runs.current_plan"
    assert json.loads(requests[0].content) == {"run_id": "run-1"}
    with pytest.raises(ValueError):
        await client.get_current_plan("")
    assert len(requests) == 1
    await client._http_client.aclose()


@pytest.mark.asyncio
async def test_command_requires_explicit_run():
    app = MagicMock()
    processor = CommandProcessor(app)
    await processor.cmd_run("plan")
    app.open_current_plan.assert_not_called()
    await processor.cmd_run("plan run-1")
    app.open_current_plan.assert_called_once_with("run-1")


@pytest.mark.asyncio
async def test_mounted_refresh_refusal_and_expiry_clear_content():
    raw = snapshot()
    class Client(AgentClient):
        value = raw
        async def get_current_plan(self, run_id):
            return copy.deepcopy(self.value)
    client = Client()
    class PlanApp(App):
        def on_mount(self):
            self.push_screen(CurrentPlanScreen(client, "run-1"))
    app = PlanApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        widget = screen.query_one("#current-plan", Static)
        assert "literal" in str(widget.render())
        client.value = {"availability": "unavailable"}
        screen.action_refresh_plan()
        assert "literal" not in str(widget.render())
        await pilot.pause()
        assert "unavailable" in str(widget.render())
        client.value = snapshot()
        client.value["snapshot"]["expires_at"] = (datetime.now(UTC) + timedelta(seconds=.2)).isoformat()
        screen.action_refresh_plan()
        await pilot.pause()
        await asyncio.sleep(.25)
        await pilot.pause()
        assert "expired" in str(widget.render())
        assert "literal" not in str(widget.render())
    await client._http_client.aclose()


@pytest.mark.asyncio
async def test_revision_high_water_survives_unavailable_read():
    class Client(AgentClient):
        value = snapshot()
        async def get_current_plan(self, run_id):
            return copy.deepcopy(self.value)
    client = Client()
    client.value["snapshot"]["revision"] = 5
    class PlanApp(App):
        def on_mount(self):
            self.push_screen(CurrentPlanScreen(client, "run-1"))
    app = PlanApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        widget = screen.query_one("#current-plan", Static)
        assert "revision 5" in str(widget.render())
        client.value = {"availability": "unavailable"}
        screen.action_refresh_plan()
        await pilot.pause()
        client.value = snapshot()
        client.value["snapshot"]["revision"] = 4
        screen.action_refresh_plan()
        await pilot.pause()
        assert "unavailable" in str(widget.render())
        assert "literal" not in str(widget.render())
    await client._http_client.aclose()


@pytest.mark.asyncio
async def test_cancelled_read_cannot_restore_old_content():
    started = asyncio.Event()
    class Client(AgentClient):
        calls = 0
        async def get_current_plan(self, run_id):
            self.calls += 1
            if self.calls == 1:
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    return snapshot()
            return {"availability": "unavailable"}
    client = Client()
    class PlanApp(App):
        def on_mount(self):
            self.push_screen(CurrentPlanScreen(client, "run-1"))
    app = PlanApp()
    async with app.run_test() as pilot:
        await started.wait()
        app.screen.action_refresh_plan()
        await pilot.pause()
        widget = app.screen.query_one("#current-plan", Static)
        assert "unavailable" in str(widget.render())
        assert "literal" not in str(widget.render())

    await client._http_client.aclose()
