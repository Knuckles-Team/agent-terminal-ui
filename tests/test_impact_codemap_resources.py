"""Tests for the P3 advanced/admin parity slash commands.

Covers ``/impact``, ``/mcp:reload``, ``/codemap``, ``/resources``,
``/pipeline``, and ``/maintenance`` added for P3-1..P3-5 of the feature
parity audit.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from rich.table import Table

from agent_terminal_ui.commands import CommandProcessor


@pytest.fixture
def mock_app() -> MagicMock:
    """Create a mock ``AgentApp`` configured for P3 command tests."""
    app = MagicMock()
    app.notify = MagicMock()

    event_log = AsyncMock()
    event_log.write = MagicMock()
    event_log.clear = MagicMock()
    app.query_one = MagicMock(return_value=event_log)

    app._client = AsyncMock()
    app._client.get_impact = AsyncMock(
        return_value=[
            {
                "id": "n1",
                "name": "caller_fn",
                "type": "Function",
                "file": "pkg/mod.py",
                "depth": 1,
                "relationship": "CALLS",
            }
        ]
    )
    app._client.reload_mcp = AsyncMock(
        return_value={"status": "reloaded", "agents": 3, "tools": 12}
    )
    app._client.generate_codemap = AsyncMock(
        return_value={
            "status": "success",
            "codemap_id": "map-123",
            "artifact": {
                "id": "map-123",
                "mermaid": "graph TD; A-->B",
                "markdown": "# Codemap\n\nDetails here.",
            },
        }
    )
    app._client.list_resources = AsyncMock(
        return_value=[
            {
                "type": "MCP_TOOL",
                "name": "search_web",
                "description": "Query the web for info.",
            }
        ]
    )
    app._client.spawn_resource = AsyncMock(
        return_value={"id": "agent-42", "name": "research-specialist"}
    )
    app._client.get_pipeline_status = AsyncMock(
        return_value={
            "status": "idle",
            "phases": [
                {
                    "name": "scan",
                    "state": "done",
                    "last_run": "2026-01-01T00:00:00Z",
                    "progress": 1.0,
                },
                {
                    "name": "embedding",
                    "state": "pending",
                    "last_run": "",
                    "progress": 0.0,
                },
            ],
        }
    )
    app._client.trigger_pipeline = AsyncMock(
        return_value={"status": "success", "phase": "scan"}
    )
    app._client.get_maintenance_status = AsyncMock(
        return_value={
            "status": "healthy",
            "operations": [
                {
                    "name": "prune",
                    "last_run": "2026-01-02T00:00:00Z",
                    "items_pruned": 14,
                    "items_updated": 0,
                },
                {
                    "name": "reindex",
                    "last_run": "",
                    "items_pruned": 0,
                    "items_updated": 5,
                },
            ],
        }
    )
    app._client.trigger_maintenance = AsyncMock(
        return_value={"status": "success", "operation": "prune"}
    )

    app.on_input_text_area_submitted = AsyncMock()
    return app


@pytest.fixture
def processor(mock_app: MagicMock) -> CommandProcessor:
    """Create a ``CommandProcessor`` bound to the mock app."""
    return CommandProcessor(mock_app)


def _last_written(mock_app: MagicMock) -> object:
    """Return the most recent argument passed to ``event_log.write``."""
    log = mock_app.query_one.return_value
    assert log.add_info.called, "event log write was not called"
    return log.add_info.call_args[0][0]


class TestP3Registration:
    """All new P3 commands must be registered in the commands dict."""

    @pytest.mark.parametrize(
        "name",
        [
            "impact",
            "mcp:reload",
            "codemap",
            "resources",
            "pipeline",
            "maintenance",
        ],
    )
    def test_command_registered(self, processor: CommandProcessor, name: str) -> None:
        """Every P3 slash command must appear in ``processor.commands``."""
        assert name in processor.commands


class TestImpactCommand:
    """Tests for ``/impact <symbol>``."""

    @pytest.mark.asyncio
    async def test_impact_with_symbol(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/impact pkg.mod.func`` calls ``get_impact`` and renders a Table."""
        await processor.cmd_impact("pkg.mod.func")
        mock_app._client.get_impact.assert_awaited_once_with("pkg.mod.func")
        assert isinstance(_last_written(mock_app), Table)

    @pytest.mark.asyncio
    async def test_impact_without_symbol_shows_help(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/impact`` with no arg shows a help banner, no client call."""
        await processor.cmd_impact("")
        mock_app._client.get_impact.assert_not_called()
        written = _last_written(mock_app)
        assert isinstance(written, str)
        assert "/impact" in written

    @pytest.mark.asyncio
    async def test_impact_help_flag(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/impact --help`` shows usage and does not call the client."""
        await processor.cmd_impact("--help")
        mock_app._client.get_impact.assert_not_called()

    @pytest.mark.asyncio
    async def test_impact_http_error_renders_red(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """HTTP errors from the impact endpoint must render as a red line."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 500
        mock_app._client.get_impact.side_effect = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=response
        )

        await processor.cmd_impact("pkg.mod.func")

        last = _last_written(mock_app)
        assert isinstance(last, str)
        assert "[red]" in last
        assert "500" in last


class TestMcpReloadCommand:
    """Tests for ``/mcp:reload``."""

    @pytest.mark.asyncio
    async def test_mcp_reload_success(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/mcp:reload`` reports the number of reloaded servers."""
        await processor.cmd_mcp_reload("")
        mock_app._client.reload_mcp.assert_awaited_once()
        mock_app.notify.assert_called()
        assert "reloaded" in mock_app.notify.call_args[0][0].lower()

        last = _last_written(mock_app)
        assert isinstance(last, str)
        assert "3" in last and "12" in last

    @pytest.mark.asyncio
    async def test_mcp_reload_backend_error(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Backend-reported errors should render as a red line."""
        mock_app._client.reload_mcp.return_value = {
            "status": "error",
            "error": "kaboom",
        }

        await processor.cmd_mcp_reload("")

        last = _last_written(mock_app)
        assert isinstance(last, str)
        assert "[red]" in last
        assert "kaboom" in last


class TestCodemapCommand:
    """Tests for ``/codemap <prompt>``."""

    @pytest.mark.asyncio
    async def test_codemap_generates(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/codemap <prompt>`` calls ``generate_codemap`` with the prompt."""
        await processor.cmd_codemap("render auth flow")
        mock_app._client.generate_codemap.assert_awaited_once_with("render auth flow")

    @pytest.mark.asyncio
    async def test_codemap_requires_prompt(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/codemap`` without args should notify and skip the call."""
        await processor.cmd_codemap("")
        mock_app.notify.assert_called()
        mock_app._client.generate_codemap.assert_not_called()

    @pytest.mark.asyncio
    async def test_codemap_backend_error(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Backend error status should render as a red line."""
        mock_app._client.generate_codemap.return_value = {
            "status": "error",
            "message": "graph offline",
        }

        await processor.cmd_codemap("render auth flow")

        last = _last_written(mock_app)
        assert isinstance(last, str)
        assert "[red]" in last
        assert "graph offline" in last


class TestResourcesCommand:
    """Tests for ``/resources``."""

    @pytest.mark.asyncio
    async def test_resources_default_lists(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Bare ``/resources`` lists callable resources."""
        await processor.cmd_resources("")
        mock_app._client.list_resources.assert_awaited_once()
        assert isinstance(_last_written(mock_app), Table)

    @pytest.mark.asyncio
    async def test_resources_list_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/resources list`` lists callable resources."""
        await processor.cmd_resources("list")
        mock_app._client.list_resources.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resources_spawn_with_json(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/resources spawn <json>`` decodes JSON and calls spawn_resource."""
        await processor.cmd_resources(
            'spawn {"agent_type": "specialist", "task": "demo"}'
        )
        mock_app._client.spawn_resource.assert_awaited_once_with(
            {"agent_type": "specialist", "task": "demo"}
        )
        mock_app.notify.assert_called()

    @pytest.mark.asyncio
    async def test_resources_spawn_invalid_json(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Malformed JSON must notify and not reach the backend."""
        await processor.cmd_resources("spawn {not-json")
        mock_app._client.spawn_resource.assert_not_called()
        mock_app.notify.assert_called()

    @pytest.mark.asyncio
    async def test_resources_spawn_requires_object(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Non-object JSON (e.g. a list) is rejected."""
        await processor.cmd_resources("spawn [1, 2, 3]")
        mock_app._client.spawn_resource.assert_not_called()
        mock_app.notify.assert_called()

    @pytest.mark.asyncio
    async def test_resources_spawn_requires_args(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/resources spawn`` alone must notify."""
        await processor.cmd_resources("spawn")
        mock_app._client.spawn_resource.assert_not_called()
        mock_app.notify.assert_called()


class TestPipelineCommand:
    """Tests for ``/pipeline``."""

    @pytest.mark.asyncio
    async def test_pipeline_default_status(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Bare ``/pipeline`` should show status."""
        await processor.cmd_pipeline("")
        mock_app._client.get_pipeline_status.assert_awaited_once()
        assert isinstance(_last_written(mock_app), Table)

    @pytest.mark.asyncio
    async def test_pipeline_status_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/pipeline status`` should show status."""
        await processor.cmd_pipeline("status")
        mock_app._client.get_pipeline_status.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pipeline_run_without_phase(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/pipeline run`` should trigger the whole pipeline."""
        await processor.cmd_pipeline("run")
        mock_app._client.trigger_pipeline.assert_awaited_once_with(None)
        mock_app.notify.assert_called()

    @pytest.mark.asyncio
    async def test_pipeline_run_with_phase(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/pipeline run scan`` should trigger a specific phase."""
        await processor.cmd_pipeline("run scan")
        mock_app._client.trigger_pipeline.assert_awaited_once_with("scan")

    @pytest.mark.asyncio
    async def test_pipeline_unknown_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Unknown subcommands notify and do not call the client."""
        await processor.cmd_pipeline("bogus")
        mock_app.notify.assert_called()
        mock_app._client.get_pipeline_status.assert_not_called()


class TestMaintenanceCommand:
    """Tests for ``/maintenance``."""

    @pytest.mark.asyncio
    async def test_maintenance_default_status(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Bare ``/maintenance`` should show status."""
        await processor.cmd_maintenance("")
        mock_app._client.get_maintenance_status.assert_awaited_once()
        assert isinstance(_last_written(mock_app), Table)

    @pytest.mark.asyncio
    async def test_maintenance_status_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/maintenance status`` should show status."""
        await processor.cmd_maintenance("status")
        mock_app._client.get_maintenance_status.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_maintenance_run_without_operation(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/maintenance run`` should trigger without a specific operation."""
        await processor.cmd_maintenance("run")
        mock_app._client.trigger_maintenance.assert_awaited_once_with(None)
        mock_app.notify.assert_called()

    @pytest.mark.asyncio
    async def test_maintenance_run_with_operation(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/maintenance run prune`` should forward the operation name."""
        await processor.cmd_maintenance("run prune")
        mock_app._client.trigger_maintenance.assert_awaited_once_with("prune")

    @pytest.mark.asyncio
    async def test_maintenance_unknown_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Unknown subcommands notify and do not call the client."""
        await processor.cmd_maintenance("bogus")
        mock_app.notify.assert_called()
        mock_app._client.get_maintenance_status.assert_not_called()


class TestP3ClientMethods:
    """Smoke tests for the P3 ``AgentClient`` method surface."""

    @pytest.mark.parametrize(
        "method",
        [
            "get_impact",
            "reload_mcp",
            "generate_codemap",
            "list_resources",
            "spawn_resource",
            "get_pipeline_status",
            "trigger_pipeline",
            "get_maintenance_status",
            "trigger_maintenance",
        ],
    )
    def test_client_has_method(self, method: str) -> None:
        """``AgentClient`` must expose every new P3 method."""
        from agent_terminal_ui.client import AgentClient

        assert callable(getattr(AgentClient, method, None)), (
            f"AgentClient must define {method!r}"
        )
