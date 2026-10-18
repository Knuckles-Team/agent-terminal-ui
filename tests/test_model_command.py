"""Tests for the multi-model ``/model`` slash command.

Covers the three registry-backed subcommands (``list``, ``show``,
``set <id>``), the empty-registry fallback, an unknown-id error case, and
unavailable selection without model state changes.
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
@pytest.mark.parametrize("command", ["set cloud-mini", "cloud-mini", "set unlisted-model", "unlisted-model"])
@pytest.mark.parametrize("previous", [None, "previous-model"])
async def test_model_selection_is_unavailable_without_mutation(processor, mock_app, command, previous):
    mock_app._current_model = previous
    mock_app._current_model_id = previous
    await processor.cmd_model(command)
    assert mock_app._current_model == previous
    assert mock_app._current_model_id == previous
    assert mock_app._client.mock_calls == []
    expected = (
        "Model selection is unavailable through this Arbora connection; "
        "no model change was sent."
    )
    mock_app.notify.assert_called_once_with(expected, severity="warning")
    assert expected in mock_app.query_one.return_value.add_info.call_args.args[0]


@pytest.mark.asyncio
async def test_model_details_do_not_claim_server_selection(processor, mock_app):
    await processor.cmd_model("set cloud-mini")
    await processor.cmd_model("show")
    panel = mock_app.query_one.return_value.add_info.call_args.args[0]
    assert "Active" not in str(panel.title)
    assert "model selection is unavailable" in str(panel.renderable).lower()
    await processor.cmd_model("list")
    messages = mock_app.query_one.return_value.add_info.call_args_list
    table = messages[-2].args[0]
    assert "Active" not in [column.header for column in table.columns]
    assert "model selection is unavailable" in messages[-1].args[0].lower()
