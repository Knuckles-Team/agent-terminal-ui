"""No unbound filesystem log fallback."""

# spec: TUI-RUNTIME-R002.9

import builtins
import io
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from textual.widgets import RichLog

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.tui.input_text_area import InputTextArea


@pytest.mark.asyncio
async def test_unbound_log_path_is_never_opened_and_both_controls_refuse(
    app: AgentApp, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "shared-tenant.log"
    log_path.write_text("other-tenant secret\n")
    monkeypatch.setenv("AGENT_LOG_FILE", str(log_path))
    attempts: list[object] = []
    original_open = builtins.open
    original_io_open = io.open

    def checked_open(file, *args, **kwargs):
        if str(file) == str(log_path):
            attempts.append(file)
            raise AssertionError("unbound log file opened")
        return original_open(file, *args, **kwargs)

    def checked_io_open(file, *args, **kwargs):
        if str(file) == str(log_path):
            attempts.append(file)
            raise AssertionError("unbound log file opened")
        return original_io_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", checked_open)
    monkeypatch.setattr(io, "open", checked_io_open)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        log = app.screen.query_one("#server-log", RichLog)
        assert not log.display
        log.write("stale protected content")
        await app._cmd_processor.cmd_logs("")
        await pilot.pause()
        assert log.display
        rendered = "".join(line.text for line in log.lines)
        assert "authenticated host reader is required" in rendered
        assert "stale protected content" not in rendered
        assert "other-tenant" not in rendered
        assert log.markup is False
        await pilot.press("ctrl+v")
        await pilot.pause()
        assert not log.display
        await pilot.press("ctrl+v")
        await pilot.pause()
        assert log.display
        assert "authenticated host reader is required" in "".join(
            line.text for line in log.lines
        )
        assert app.screen.query_one(InputTextArea).disabled is False
        assert attempts == []
    assert attempts == []


@pytest.mark.asyncio
async def test_missing_log_source_does_not_call_client_for_logs(
    app: AgentApp, fake_client: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AGENT_LOG_FILE", raising=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        calls = list(fake_client.mock_calls)
        await app._cmd_processor.cmd_logs("")
        await pilot.pause()
        assert fake_client.mock_calls == calls
        assert app.screen.query_one("#server-log", RichLog).display
