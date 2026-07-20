"""Tests for the multi-model ``/model`` slash command.

Covers the three registry-backed subcommands (``list``, ``show``,
``set <id>``), the empty-registry fallback, an unknown-id error case, and
the end-to-end flow where ``set`` primes the shared
``_current_model`` attribute that the client picks up on the next turn.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_terminal_ui.commands import CommandProcessor

SAMPLE_REGISTRY = {
    "default_id": "local-fast",
    "models": [
        {
            "id": "local-fast",
            "name": "Local LM Studio",
            "provider": "openai",
            "model_id": "llama-3.2-3b-instruct",
            "base_url": "http://localhost:1234/v1",
            "api_key_env": None,
            "tier": "light",
            "tags": [],
            "cost": {"input": 0.0, "output": 0.0},
            "context_window": None,
            "max_output_tokens": None,
            "is_default": True,
        },
        {
            "id": "cloud-mini",
            "name": "GPT-4o Mini",
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "base_url": None,
            "api_key_env": "OPENAI_API_KEY",
            "tier": "medium",
            "tags": ["code", "tools"],
            "cost": {"input": 0.15, "output": 0.6},
            "context_window": None,
            "max_output_tokens": None,
            "is_default": False,
        },
        {
            "id": "cloud-opus",
            "name": "Claude 3 Opus",
            "provider": "anthropic",
            "model_id": "claude-3-opus-20240229",
            "base_url": None,
            "api_key_env": "ANTHROPIC_API_KEY",
            "tier": "heavy",
            "tags": ["reasoning", "tools"],
            "cost": {"input": 15.0, "output": 75.0},
            "context_window": None,
            "max_output_tokens": None,
            "is_default": False,
        },
    ],
}


@pytest.fixture
def mock_app():
    """Create a mock AgentApp with a registry-aware stub client."""
    app = MagicMock()
    app.notify = MagicMock()

    event_log = AsyncMock()
    event_log.write = MagicMock()
    event_log.clear = MagicMock()
    app.query_one.return_value = event_log

    app._client = AsyncMock()
    app._client.list_configured_models = AsyncMock(return_value=SAMPLE_REGISTRY)
    app._current_model = None
    app._current_model_id = None
    return app


@pytest.fixture
def processor(mock_app):
    return CommandProcessor(mock_app)


@pytest.mark.asyncio
async def test_model_list_renders_registry(processor, mock_app):
    await processor.cmd_model("")
    mock_app._client.list_configured_models.assert_awaited_once()
    event_log = mock_app.query_one.return_value
    assert event_log.add_info.called
    args_written = [call.args[0] for call in event_log.add_info.call_args_list]
    # First write is the rich Table, second write is the dim help hint.
    assert any(
        hasattr(a, "title") and "Configured Models" in str(a.title)
        for a in args_written
    )


@pytest.mark.asyncio
async def test_model_list_explicit_subcommand(processor, mock_app):
    await processor.cmd_model("list")
    mock_app._client.list_configured_models.assert_awaited_once()


@pytest.mark.asyncio
async def test_model_show_defaults_to_registry_default(processor, mock_app):
    await processor.cmd_model("show")
    event_log = mock_app.query_one.return_value
    assert event_log.add_info.called
    (panel,) = event_log.add_info.call_args_list[-1].args
    rendered = str(panel.renderable)
    assert "local-fast" in rendered
    assert "light" in rendered


@pytest.mark.asyncio
async def test_model_show_reflects_current_override(processor, mock_app):
    mock_app._current_model_id = "cloud-opus"
    await processor.cmd_model("show")
    event_log = mock_app.query_one.return_value
    (panel,) = event_log.add_info.call_args_list[-1].args
    rendered = str(panel.renderable)
    assert "cloud-opus" in rendered
    assert "heavy" in rendered


@pytest.mark.asyncio
async def test_model_set_updates_current_model(processor, mock_app):
    await processor.cmd_model("set cloud-mini")
    assert mock_app._current_model_id == "cloud-mini"
    # ``_current_model`` is what the client uses when sending a turn.
    assert mock_app._current_model == "cloud-mini"
    mock_app.notify.assert_called()
    event_log = mock_app.query_one.return_value
    # Last write must confirm the switch in green.
    last_message = event_log.add_info.call_args_list[-1].args[0]
    assert "cloud-mini" in last_message
    assert "green" in last_message.lower()


@pytest.mark.asyncio
async def test_model_set_rejects_unknown_id(processor, mock_app):
    await processor.cmd_model("set does-not-exist")
    # Override is NOT applied on failure.
    assert mock_app._current_model_id is None
    event_log = mock_app.query_one.return_value
    last_message = event_log.add_info.call_args_list[-1].args[0]
    assert "does-not-exist" in last_message
    assert "not found" in last_message.lower()


@pytest.mark.asyncio
async def test_model_set_requires_argument(processor, mock_app):
    await processor.cmd_model("set")
    event_log = mock_app.query_one.return_value
    last_message = event_log.add_info.call_args_list[-1].args[0]
    assert "Usage" in last_message
    assert mock_app._current_model_id is None


@pytest.mark.asyncio
async def test_model_list_empty_registry(processor, mock_app):
    mock_app._client.list_configured_models = AsyncMock(
        return_value={"models": [], "default_id": None}
    )
    await processor.cmd_model("list")
    event_log = mock_app.query_one.return_value
    last_message = event_log.add_info.call_args_list[-1].args[0]
    assert "No models configured" in last_message


@pytest.mark.asyncio
async def test_model_legacy_shorthand_unknown_id(processor, mock_app):
    """Bare ``/model <id>`` is a legacy shorthand and tolerates unknown ids.

    This mirrors the existing workflow where users pass raw provider model
    strings (e.g. ``/model claude-3-opus-20240229``) and the server-side
    override still applies even if the id isn't in the registry.
    """
    await processor.cmd_model("claude-3-opus-20240229")
    assert mock_app._current_model_id == "claude-3-opus-20240229"
    assert mock_app._current_model == "claude-3-opus-20240229"


@pytest.mark.asyncio
async def test_model_legacy_shorthand_known_id_uses_set_flow(processor, mock_app):
    """When the shorthand id is in the registry, the richer ``set`` flow
    runs (including the provider:model suffix in the confirmation)."""
    await processor.cmd_model("cloud-mini")
    assert mock_app._current_model_id == "cloud-mini"
    event_log = mock_app.query_one.return_value
    last_message = event_log.add_info.call_args_list[-1].args[0]
    assert "gpt-4o-mini" in last_message
