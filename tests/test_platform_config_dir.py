"""Graph OS platform config location with the one-release legacy fallback."""

from __future__ import annotations

import pytest

from agent_terminal_ui import settings


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("GRAPH_OS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("AGENT_UTILITIES_CONFIG_DIR", raising=False)
    monkeypatch.setattr(settings, "_legacy_config_warned", False)
    calls: list[tuple] = []
    monkeypatch.setattr(
        settings.logger, "warning", lambda msg, *args: calls.append(args)
    )
    return calls


def _write(directory, name="config.json"):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text("{}")


def test_env_override(monkeypatch, tmp_path, _isolated):
    monkeypatch.setenv("GRAPH_OS_CONFIG_DIR", str(tmp_path / "custom"))
    _write(tmp_path / "custom")
    assert settings.get_agent_utilities_config_dir() == tmp_path / "custom"
    assert _isolated == []


def test_new_path(tmp_path, _isolated):
    _write(tmp_path / "xdg" / "graph-os")
    _write(tmp_path / "xdg" / "agent-utilities")
    assert settings.get_agent_utilities_config_dir() == tmp_path / "xdg" / "graph-os"
    assert _isolated == []


def test_fallback_warns_once(tmp_path, _isolated):
    legacy = tmp_path / "xdg" / "agent-utilities"
    _write(legacy)
    assert settings.platform_config_file("config.json") == legacy / "config.json"
    assert settings.get_agent_utilities_config_dir() == legacy
    assert _isolated == [(legacy / "config.json", tmp_path / "xdg" / "graph-os")]


def test_neither_present(tmp_path, _isolated):
    assert settings.platform_config_file("config.json") == (
        tmp_path / "xdg" / "graph-os" / "config.json"
    )
    assert _isolated == []
