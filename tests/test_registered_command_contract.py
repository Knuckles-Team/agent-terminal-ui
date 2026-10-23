"""Dispatcher contracts and served usage entry points, not full matrix acceptance."""

import inspect
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from arbora.client._generated_models import REGISTRY_DIGEST
from textual.app import App
from textual.widgets import Static

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.client import AgentClient
from agent_terminal_ui.commands import CommandProcessor
from agent_terminal_ui.screens.usage import UsageScreen
from agent_terminal_ui.tui.input_text_area import InputTextArea

pytestmark = pytest.mark.spec("TUI-RUNTIME-R012.4.3.1")


@pytest.mark.parametrize("name", sorted(CommandProcessor(object()).commands))
def test_every_registered_handler_accepts_dispatch_arguments(name: str) -> None:
    """Registry additions must accept the dispatcher's positional argument."""
    handler = CommandProcessor(object()).commands[name]
    inspect.signature(handler).bind("")


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/focus", "/focus "])
async def test_focus_dispatch_toggles_sidebar_without_error(
    command: str, fake_client: AsyncMock
) -> None:
    fake_client.stream = Mock(side_effect=AssertionError("focus must not start a turn"))
    app = AgentApp(client=fake_client)
    async with app.run_test(size=(120, 35)) as pilot:
        sidebar = app.screen.query_one("#sidebar")
        composer = app.screen.query_one(InputTextArea)
        initially_visible = sidebar.display
        assert app.focused is composer
        for expected in (not initially_visible, initially_visible):
            composer.load_text(command)
            await pilot.press("enter")
            await pilot.pause()
            assert sidebar.display is expected
            assert composer.text == ""
            assert app.focused is composer
            fake_client.stream.assert_not_called()
        assert not app._is_processing


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["usage", "stats", "cost", "context"])
@pytest.mark.parametrize("refused", [False, True])
async def test_usage_entry_points_reach_only_served_operation(
    command: str, refused: bool
) -> None:
    requests: list[httpx.Request] = []

    def reply(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        envelope = {
            "meta": {"registry_digest": REGISTRY_DIGEST},
            "ok": not refused,
        }
        if refused:
            envelope["error"] = {"code": "UNAVAILABLE"}
        else:
            envelope["result"] = {"value": {"totals": {"tokens": 42}}}
        return httpx.Response(200, json=envelope)

    client = AgentClient()
    await client._http_client.aclose()
    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as transport:
        client._http_client = transport

        class UsageCommandApp(App):
            agent_client = client
            action_switch_usage = AgentApp.action_switch_usage

            def compose(self) -> Iterator[Static]:
                yield Static("Command harness")

        app = UsageCommandApp()
        async with app.run_test() as pilot:
            assert await CommandProcessor(app).process(f"/{command}")
            await pilot.pause()
            assert isinstance(app.screen, UsageScreen)
            await app.workers.wait_for_complete()
            rendered = str(app.screen.query_one("#usage-hist", Static).render())
            if refused:
                assert rendered.count("unavailable") == 1
                assert "usage.read" in rendered
                assert "42" not in rendered
            else:
                assert "tokens: 42" in rendered
            assert [(request.method, request.url.path) for request in requests] == [
                ("POST", "/api/v1/ops/usage.read")
            ]


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/queue", "/queue "])
@pytest.mark.parametrize("typed", [False, True])
async def test_exact_queue_command_never_selects_clear(
    command: str, typed: bool, fake_client: AsyncMock
) -> None:
    fake_client.stream = Mock(side_effect=AssertionError("queue must not start a turn"))
    app = AgentApp(client=fake_client)
    app._user_message_queue = [{"message": "preserve this queued message"}]
    async with app.run_test(size=(120, 35)) as pilot:
        composer = app.screen.query_one(InputTextArea)
        if typed:
            await pilot.press(*command)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            composer.focus()
        else:
            composer.load_text(command)
        await pilot.press("enter")
        await pilot.pause()
        assert composer.text == ""
        await pilot.press("enter")
        await pilot.pause()
        assert app._user_message_queue == [{"message": "preserve this queued message"}]
        fake_client.stream.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/c", "/", "/queu"])
async def test_ambiguous_command_does_not_select_a_sibling(
    command: str, fake_client: AsyncMock
) -> None:
    fake_client.stream = Mock(side_effect=AssertionError("unknown command must not turn"))
    app = AgentApp(client=fake_client)
    async with app.run_test(size=(120, 35)) as pilot:
        composer = app.screen.query_one(InputTextArea)
        composer.load_text(command)
        await pilot.press("enter")
        await pilot.pause()
        assert composer.text == ""
        fake_client.stream.assert_not_called()


@pytest.mark.asyncio
async def test_unique_partial_command_completes_without_submitting(
    fake_client: AsyncMock,
) -> None:
    fake_client.stream = Mock(side_effect=AssertionError("completion must not turn"))
    app = AgentApp(client=fake_client)
    async with app.run_test(size=(120, 35)) as pilot:
        composer = app.screen.query_one(InputTextArea)
        sidebar = app.screen.query_one("#sidebar")
        initially_visible = sidebar.display
        composer.load_text("/foc")
        await pilot.press("enter")
        await pilot.pause()
        assert composer.text == "/focus "
        assert sidebar.display is initially_visible
        await pilot.press("enter")
        await pilot.pause()
        assert sidebar.display is not initially_visible
        assert composer.text == ""
        fake_client.stream.assert_not_called()
