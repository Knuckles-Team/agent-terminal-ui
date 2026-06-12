"""Shared fixtures for the agent-terminal-ui test suite.

Centralizes the mock ``AgentClient`` and ``AgentApp`` construction that the
individual test modules previously duplicated, and isolates session state to a
temporary directory so tests never touch a developer's real database.
"""

import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("AGENT_UTILITIES_TESTING", "true")


@pytest.fixture
def isolated_data_dir(tmp_path: Path) -> Iterator[Path]:
    """Point session/task persistence at a throwaway directory."""
    prev = os.environ.get("AGENT_UTILITIES_DATA_DIR")
    os.environ["AGENT_UTILITIES_DATA_DIR"] = str(tmp_path)
    try:
        yield tmp_path
    finally:
        if prev is None:
            os.environ.pop("AGENT_UTILITIES_DATA_DIR", None)
        else:
            os.environ["AGENT_UTILITIES_DATA_DIR"] = prev


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

    async def _empty_stream(*_args, **_kwargs):
        for _ in ():
            yield _

    client.stream = _empty_stream
    return client


@pytest.fixture
def app(fake_client: AsyncMock, isolated_data_dir: Path):
    """A fresh ``AgentApp`` wired to the fake client (not yet mounted)."""
    from agent_terminal_ui.app import AgentApp

    return AgentApp(client=fake_client)
