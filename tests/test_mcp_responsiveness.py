"""Mounted MCP reads remain cancellable and never submit a model turn."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from textual.widgets import DataTable, Static

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.client import ArboraOperationError
from agent_terminal_ui.tui.input_text_area import InputTextArea
from agent_terminal_ui.tui.mcp_screen import MCPScreen

pytestmark = [pytest.mark.asyncio, pytest.mark.spec("TUI-RUNTIME-R012.4.2")]


@pytest.mark.parametrize("stage", ["status", "catalog"])
async def test_mcp_opens_before_read_and_close_discards_late_completion(
    fake_client: AsyncMock, stage: str,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def delayed() -> Any:
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()
        return {"children": {"old": {}}} if stage == "status" else [
            {"id": "old", "name": "Old", "description": "Old"}
        ]

    fake_client.get_mcp_config.return_value = {"children": {}}
    operation = fake_client.get_mcp_config if stage == "status" else fake_client.list_mcp_tools
    operation.side_effect = delayed
    fake_client.stream = Mock(side_effect=AssertionError("MCP must not start a turn"))
    app = AgentApp(client=fake_client)
    async with app.run_test() as pilot:
        composer = app.screen.query_one(InputTextArea)
        composer.load_text("/mcp")
        submit = asyncio.create_task(pilot.press("enter"))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            await asyncio.sleep(0.1)
            assert isinstance(app.screen, MCPScreen)
            screen = app.screen
            assert "Loading" in str(screen.query_one("#mcp-status", Static).content)
            await pilot.press("escape")
            assert app.screen is not screen
            assert app.focused is composer
            operation.side_effect = None
            fake_client.get_mcp_config.return_value = {"children": {}}
            composer.load_text("/mcp")
            await pilot.press("enter")
            await pilot.pause()
            fresh = app.screen
            assert isinstance(fresh, MCPScreen)
            release.set()
            await pilot.pause()
            assert app.screen is fresh
            assert "Visible Servers: 0" in str(fresh.query_one("#mcp-status", Static).content)
            assert fake_client.list_mcp_tools.await_count == (1 if stage == "status" else 2)
            await pilot.press("escape")
            fake_client.stream.assert_not_called()
        finally:
            release.set()
            await submit


@pytest.mark.parametrize("error", [
    ArboraOperationError("DENIED"), ValueError("malformed [payload]"),
    httpx.ReadTimeout("timed out"),
])
async def test_mcp_retry_clears_data_and_distinguishes_failure_from_empty(
    fake_client: AsyncMock, error: Exception,
) -> None:
    fake_client.get_mcp_config.return_value = {"children": {"server": {}}}
    fake_client.list_mcp_tools.return_value = [{"id": "old", "name": "Old", "description": "Old"}]
    app = AgentApp(client=fake_client)
    async with app.run_test() as pilot:
        app.screen.query_one(InputTextArea).load_text("/mcp")
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, MCPScreen)
        assert screen.query_one(DataTable).row_count == 1
        fake_client.list_mcp_tools.side_effect = error
        await pilot.press("r")
        await pilot.pause()
        assert screen.query_one(DataTable).row_count == 0
        status = str(screen.query_one("#mcp-status", Static).content)
        assert "unavailable" in status
        assert str(error) in status
        fake_client.list_mcp_tools.side_effect = None
        fake_client.get_mcp_config.return_value = {"children": {}}
        fake_client.list_mcp_tools.return_value = []
        await pilot.press("r")
        await pilot.pause()
        assert "Visible Servers: 0" in str(screen.query_one("#mcp-status", Static).content)
        assert "No tools" in str(screen.query_one("#mcp-status", Static).content)
        await pilot.press("escape")


@pytest.mark.parametrize("change", ["refresh", "owner"])
@pytest.mark.parametrize("stage", ["status", "catalog"])
@pytest.mark.parametrize("late_failure", [False, True])
async def test_mcp_superseded_reads_cannot_publish_or_continue(
    fake_client: AsyncMock, change: str, stage: str, late_failure: bool,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()
    calls = 0

    async def delayed() -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            completed.set()
            if late_failure:
                raise ArboraOperationError("OLD_DENIED")
            return {"children": {"old": {}}} if stage == "status" else [
                {"id": "old", "name": "Old", "description": "Old"}
            ]
        return {"children": {}} if stage == "status" else []

    fake_client.get_mcp_config.return_value = {"children": {}}
    operation = fake_client.get_mcp_config if stage == "status" else fake_client.list_mcp_tools
    operation.side_effect = delayed
    fake_client.stream = Mock(side_effect=AssertionError("MCP must not start a turn"))
    app = AgentApp(client=fake_client)
    async with app.run_test() as pilot:
        app.screen.query_one(InputTextArea).load_text("/mcp")
        try:
            await pilot.press("enter")
            await asyncio.wait_for(entered.wait(), 2)
            screen = app.screen
            assert isinstance(screen, MCPScreen)
            if change == "refresh":
                await pilot.press("r")
                await pilot.pause()
            else:
                app._client = AsyncMock()
            release.set()
            await asyncio.wait_for(completed.wait(), 2)
            await pilot.pause()
            status = str(screen.query_one("#mcp-status", Static).content)
            assert "OLD_DENIED" not in status
            assert "client changed" in status if change == "owner" else "Visible Servers: 0" in status
            assert screen.query_one(DataTable).row_count == 0
            assert not screen.mcp_tools
            if stage == "status":
                assert fake_client.list_mcp_tools.await_count == (1 if change == "refresh" else 0)
            if change == "owner":
                reads = fake_client.get_mcp_config.await_count
                await pilot.press("r")
                await pilot.pause()
                assert fake_client.get_mcp_config.await_count == reads
            await pilot.press("escape")
            fake_client.stream.assert_not_called()
        finally:
            release.set()
            app._client = fake_client
