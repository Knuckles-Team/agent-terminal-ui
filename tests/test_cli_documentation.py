"""Truthful Python entry-point documentation and parser contracts."""

# spec: TUI-RUNTIME-R015.30.1
# spec: TUI-RUNTIME-R015.41.1
# spec: TUI-RUNTIME-R015.42.1

import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent_terminal_ui import headless
from agent_terminal_ui.session_manager import get_shared_db_path
from agent_terminal_ui.settings import get_agent_utilities_config_dir
from agent_terminal_ui.terminal_ui import terminal_ui

ROOT = Path(__file__).resolve().parents[1]


def test_actual_help_matches_operator_documentation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["agent-terminal-ui", "--help"])
    with pytest.raises(SystemExit) as exc:
        terminal_ui()
    assert exc.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    docs = (ROOT / "docs/configuration.md").read_text()
    readme = (ROOT / "README.md").read_text()
    flags = set(re.findall(r"--[a-z][a-z-]*", help_text))
    assert flags == {
        "--help", "--prompt", "--override", "--bg", "--headless", "--model",
        "--session", "--mode", "--observe-task",
    }
    assert all(flag in docs and flag in readme for flag in flags)
    assert "ignored by the A2A transport" in help_text
    assert "does not load prior turns for the model" in help_text
    assert "server selects" in help_text
    assert "Model id for headless runs" not in help_text
    assert "Continue the Arbora conversation" not in help_text
    assert "compatibility" in docs.lower()
    assert "does not load prior turns" in docs


@pytest.mark.parametrize("mode", ["ask", "plan", "build"])
def test_documented_headless_mode_and_context_dispatch(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = AsyncMock(return_value=True)
    monkeypatch.setattr(headless, "run_headless", run)
    monkeypatch.setattr(sys, "argv", [
        "agent-terminal-ui", "--headless", "--prompt", "new turn",
        "--session", "context-1", "--mode", mode, "--model", "compatibility-id",
    ])
    terminal_ui()
    run.assert_awaited_once_with(
        "new turn", mode_id=mode, model="compatibility-id", session_id="context-1"
    )


@pytest.mark.parametrize("args", [
    ["--headless"], ["--mode", "invalid"],
    ["--observe-task", " "], ["--observe-task", "x" * 513],
    ["--observe-task", "task", "--prompt", "new"],
    ["--observe-task", "task", "--session", "context"],
    ["--observe-task", "task", "--model", "model"],
    ["--observe-task", "task", "--mode", "build"],
    ["--observe-task", "task", "--bg"],
    ["--observe-task", "task", "--override"],
])
def test_invalid_documented_combinations_do_not_dispatch(
    args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    run = AsyncMock()
    observe = AsyncMock()
    monkeypatch.setattr(headless, "run_headless", run)
    monkeypatch.setattr(headless, "run_task_observer", observe)
    monkeypatch.setattr(sys, "argv", ["agent-terminal-ui", *args])
    with pytest.raises(SystemExit) as exc:
        terminal_ui()
    assert exc.value.code == 2
    run.assert_not_called()
    observe.assert_not_called()


@pytest.mark.parametrize("headless_flag", [[], ["--headless"]])
def test_documented_observer_is_read_only(
    headless_flag: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    observe = AsyncMock(return_value=True)
    run = AsyncMock()
    monkeypatch.setattr(headless, "run_task_observer", observe)
    monkeypatch.setattr(headless, "run_headless", run)
    monkeypatch.setattr(sys, "argv", [
        "agent-terminal-ui", "--observe-task", "task-1", *headless_flag,
    ])
    terminal_ui()
    observe.assert_awaited_once_with("task-1")
    run.assert_not_called()


def test_documented_directory_override_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = tmp_path / "config"
    data = tmp_path / "data"
    monkeypatch.setenv("AGENT_UTILITIES_CONFIG_DIR", str(config))
    monkeypatch.setenv("AGENT_UTILITIES_DATA_DIR", str(data))
    assert get_agent_utilities_config_dir() == config
    assert get_shared_db_path("sessions.db") == data / "sessions.db"
    monkeypatch.delenv("AGENT_UTILITIES_DATA_DIR")
    assert get_shared_db_path("sessions.db") == (
        tmp_path / "share" / "agent-utilities" / "sessions.db"
    )
    docs = (ROOT / "docs/configuration.md").read_text()
    assert "Takes precedence over the configuration-relative fallback" in docs
    assert "sibling `share/agent-utilities`" in docs


def test_theme_and_log_documentation_describes_refusal_not_access() -> None:
    docs = (ROOT / "docs/configuration.md").read_text()
    assert "Unknown names fall back to `tokyo-night`" in docs
    assert "`AGENT_LOG_FILE` | ignored" in docs
    assert "Never opened by the main screen" in docs
    assert "require an authenticated host reader" in docs
