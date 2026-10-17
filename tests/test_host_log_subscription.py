"""Bounded authenticated HTTP log handoff in the mounted terminal."""
# spec: TUI-RUNTIME-R002.10

import asyncio
import time
from dataclasses import replace
from unittest.mock import AsyncMock

import httpx
import pytest
from textual.widgets import RichLog

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.host_logs import AuthenticatedHostLogReader
from agent_terminal_ui.tui.input_text_area import InputTextArea


def receipt_payload():
    return dict(
        version=1,
        log_ref="opaque",
        host_instance="host",
        workspace="workspace",
        tenant="tenant",
        principal="principal",
        session_ref="session",
        policy_revision="policy",
        grant_revision="grant",
        expires_at_ms=int(time.time() * 1000) + 60000,
        interface_mode="terminal",
        web_logs=True,
        ready=True,
    )


@pytest.mark.asyncio
async def test_mounted_display_denial_clear_and_borrowed_clients(
    fake_client: AsyncMock,
) -> None:
    denied = False
    cursors = []

    async def handler(request: httpx.Request) -> httpx.Response:
        import json

        if request.url.path.endswith("reference"):
            return httpx.Response(200, json=receipt_payload())
        if denied:
            return httpx.Response(403)
        cursors.append(json.loads(request.content)["cursor"])
        return httpx.Response(
            200,
            json={
                "records": [{"message": "[red]literal\x1b control"}],
                "cursor": "next",
                "gap": False,
            },
        )

    async with httpx.AsyncClient(
        base_url="https://host/", transport=httpx.MockTransport(handler)
    ) as client:
        reader = AuthenticatedHostLogReader(client)
        receipt = await reader.bind()
        assert not reader.accepts(replace(receipt))
        app = AgentApp(client=fake_client, host_receipt=receipt, log_reader=reader)
        async with app.run_test(size=(120, 40)) as pilot:
            await app._cmd_processor.cmd_logs("")
            await pilot.pause(0.4)
            log = app.screen.query_one("#server-log", RichLog)
            text = "".join(line.text for line in log.lines)
            assert "[red]literal" in text and "\x1b" not in text
            assert log.max_lines == 1000
            assert cursors[0] is None
            denied = True
            await pilot.pause(0.4)
            text = "".join(line.text for line in log.lines)
            assert "authenticated host reader is required" in text
            assert "literal" not in text
            assert app.screen.query_one(InputTextArea).disabled is False
        fake_client.close.assert_not_awaited()
        assert not client.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"web_logs": False},
        {"web_logs": "true"},
        {"interface_mode": "web"},
        {"version": 2},
        {"expires_at_ms": 1},
        {"ready": False},
    ],
)
async def test_bad_handoff_never_reads(change) -> None:
    paths = []

    async def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json=receipt_payload() | change)

    async with httpx.AsyncClient(
        base_url="https://host/", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises((PermissionError, ValueError)):
            await AuthenticatedHostLogReader(client).bind()
    assert paths == ["/host/logs/reference"]


@pytest.mark.asyncio
async def test_payload_limit_and_refusal_invalidate_receipt() -> None:
    async def handler(request):
        if request.url.path.endswith("reference"):
            return httpx.Response(200, json=receipt_payload())
        return httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1))

    async with httpx.AsyncClient(
        base_url="https://host/", transport=httpx.MockTransport(handler)
    ) as client:
        reader = AuthenticatedHostLogReader(client)
        receipt = await reader.bind()
        with pytest.raises(ValueError):
            await reader.read(receipt.log_ref, cursor=None, limit=128)
        assert not reader.accepts(receipt)


@pytest.mark.asyncio
async def test_hide_cancels_inflight_read(fake_client: AsyncMock) -> None:
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def handler(request):
        if request.url.path.endswith("reference"):
            return httpx.Response(200, json=receipt_payload())
        entered.set()
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()
        return httpx.Response(500)

    async with httpx.AsyncClient(
        base_url="https://host/", transport=httpx.MockTransport(handler)
    ) as client:
        reader = AuthenticatedHostLogReader(client)
        receipt = await reader.bind()
        app = AgentApp(client=fake_client, host_receipt=receipt, log_reader=reader)
        async with app.run_test(size=(120, 40)) as pilot:
            await app._cmd_processor.cmd_logs("")
            await asyncio.wait_for(entered.wait(), 1)
            await pilot.press("ctrl+v")
            await asyncio.wait_for(cancelled.wait(), 1)
            assert not app.screen.query_one("#server-log", RichLog).display


@pytest.mark.asyncio
async def test_settings_cannot_expand_render_limit(fake_client: AsyncMock) -> None:
    app = AgentApp(client=fake_client)
    app.settings = {"max_log_lines": 100000}
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.screen.query_one("#server-log", RichLog).max_lines == 1000
