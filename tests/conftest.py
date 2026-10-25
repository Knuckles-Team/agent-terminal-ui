"""Shared fixtures for the agent-terminal-ui test suite.

Centralizes the mock ``AgentClient`` and ``AgentApp`` construction that the
individual test modules previously duplicated, and isolates session state to a
temporary directory so tests do not touch developer databases or settings.
"""

import importlib
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import textual.constants

from agent_terminal_ui import settings

os.environ.setdefault("AGENT_UTILITIES_TESTING", "true")

# Disable entrance animations for all tests so widgets render at their resting
# state (deterministic snapshots, no opacity-0 captures). Textual reads this
# constant into App.animation_level at construction time, so patching the module
# attribute here is order-independent (the TEXTUAL_ANIMATIONS env var is captured
# at textual import time, which may precede pytest-env).
textual.constants.TEXTUAL_ANIMATIONS = "none"


@pytest.fixture
def current_public_run_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject two pinned current-main schema lookups, not released SDK support.

    Keep the installed invoker, digest check and transport unchanged. Old-SDK
    refusal tests deliberately do not request this fixture.
    """
    models = importlib.import_module("arbora.client._generated_models")
    invoker = importlib.import_module("arbora.client.invoke")
    fixture = json.loads(
        (Path(__file__).parents[0] / "fixtures/public_run_operations.json").read_text()
    )
    original = models.schema_for

    def schema_for(operation):
        if operation in fixture["operations"]:
            return fixture["operations"][operation]
        return original(operation)

    monkeypatch.setattr(models, "schema_for", schema_for)
    monkeypatch.setattr(invoker, "schema_for", schema_for)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate shared persistence and settings, restoring all overrides afterward."""
    monkeypatch.setenv("AGENT_UTILITIES_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENT_UTILITIES_CONFIG_DIR", str(tmp_path / "global-config"))
    settings_dir = tmp_path / "terminal-config"
    monkeypatch.setattr(settings, "DEFAULT_SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(
        settings, "DEFAULT_SETTINGS_FILE", settings_dir / "settings.toml"
    )
    return tmp_path


@pytest.fixture
def fake_client() -> AsyncMock:
    """An ``AgentClient`` stand-in with the methods the UI calls stubbed out."""
    client = AsyncMock()
    client.base_url = "http://test.local"
    client.get_mcp_config = AsyncMock(return_value={"servers": [], "available": False})
    client.list_mcp_tools = AsyncMock(return_value=[])
    client.list_chats = AsyncMock(return_value=[])
    client.list_skills = AsyncMock(return_value=[])
    client.list_configured_models = AsyncMock(
        return_value={"models": [], "default_id": None}
    )
    client.get_graph_stats = AsyncMock(return_value={})
    client.search_graph = AsyncMock(return_value=[])
    client.get_dashboard_full = AsyncMock(
        return_value={"layout": {"groups": []}, "data": {}}
    )
    client.get_dashboard_data = AsyncMock(return_value={})
    # Usage/cost dashboard methods (ECO-4.41) — proper empty shapes so the
    # UsageScreen worker renders without a backend.
    client.get_usage_summary = AsyncMock(
        return_value={"totals": {}, "session_count": 0, "cache_hit_rate": 0.0}
    )
    client.get_usage_by_model = AsyncMock(return_value=[])
    client.get_usage_tools = AsyncMock(return_value=[])
    client.get_usage_activity = AsyncMock(return_value=[])
    client.get_usage_top_sessions = AsyncMock(return_value=[])
    client.get_usage_traces = AsyncMock(return_value={"enabled": False, "traces": []})

    async def _empty_stream(*_args, **_kwargs):
        for _ in ():
            yield _

    client.stream = _empty_stream
    return client


@pytest.fixture
def app(fake_client: AsyncMock):
    """A fresh ``AgentApp`` wired to the fake client (not yet mounted).

    Data-dir isolation is applied automatically via the autouse
    ``isolated_data_dir`` fixture.
    """
    from agent_terminal_ui.app import AgentApp

    return AgentApp(client=fake_client)
