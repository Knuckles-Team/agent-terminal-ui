"""Tests for the P2 feature-parity slash commands.

Covers the subcommand dispatch logic of ``/cron`` and ``/config`` added to
bring cron-task inspection and backend-configuration management into the
terminal-UI (Gap B5/B6 from the FEATURE_PARITY_AUDIT).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from rich.panel import Panel
from rich.table import Table

from agent_terminal_ui.client import AgentClient
from agent_terminal_ui.commands import CommandProcessor


@pytest.fixture
def mock_app() -> MagicMock:
    """Create a mock ``AgentApp`` configured for P2 parity-command tests."""
    app = MagicMock()
    app.notify = MagicMock()

    event_log = MagicMock()
    event_log.write = MagicMock()
    event_log.clear = MagicMock()
    app.query_one = MagicMock(return_value=event_log)

    app._client = AsyncMock()
    app._client.get_cron_calendar = AsyncMock(
        return_value=[
            {
                "id": "task-1",
                "name": "Backup",
                "schedule": "0 */4 * * *",
                "next_run": "2026-05-01T00:00:00Z",
                "last_run": "2026-04-30T20:00:00Z",
                "status": "idle",
            }
        ]
    )
    app._client.get_cron_logs = AsyncMock(
        return_value=[
            {
                "task_name": "Backup",
                "started_at": "2026-04-30T20:00:00Z",
                "duration": 42,
                "status": "success",
                "output": "ok",
            }
        ]
    )
    app._client.get_backend_config = AsyncMock(
        return_value={
            "backend_type": "LadybugBackend",
            "env_vars": {"GRAPH_BACKEND": "ladybug"},
        }
    )
    app._client.update_backend_config = AsyncMock(
        return_value={"status": "success", "message": "Restart required"}
    )
    return app


@pytest.fixture
def processor(mock_app: MagicMock) -> CommandProcessor:
    """Create a ``CommandProcessor`` bound to the mock app."""
    return CommandProcessor(mock_app)


@pytest.fixture
def client() -> AgentClient:
    """Create an ``AgentClient`` bound to a deterministic base URL."""
    return AgentClient(base_url="http://localhost:8000")


def _last_written(mock_app: MagicMock) -> object:
    """Return the most recent argument passed to ``event_log.write``."""
    log = mock_app.query_one.return_value
    assert log.write.called, "event log write was not called"
    return log.write.call_args[0][0]


def _mock_response(payload: object, status_code: int = 200) -> MagicMock:
    """Build a ``MagicMock`` that mimics an ``httpx.Response``."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = payload
    if 200 <= status_code < 300:
        response.raise_for_status = MagicMock(return_value=None)
    else:
        response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                f"HTTP {status_code}", request=MagicMock(), response=response
            )
        )
    return response


class TestCommandRegistration:
    """Verify the new P2 commands land in the command registry."""

    def test_cron_registered(self, processor: CommandProcessor) -> None:
        """``/cron`` must be exposed via the commands registry."""
        assert "cron" in processor.commands

    def test_config_registered(self, processor: CommandProcessor) -> None:
        """``/config`` must be exposed via the commands registry."""
        assert "config" in processor.commands


class TestCronCommand:
    """Subcommand dispatch for ``/cron``."""

    @pytest.mark.asyncio
    async def test_cron_default_shows_calendar(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Bare ``/cron`` should call ``get_cron_calendar`` and render a Table."""
        await processor.cmd_cron("")
        mock_app._client.get_cron_calendar.assert_awaited_once()
        assert isinstance(_last_written(mock_app), Table)

    @pytest.mark.asyncio
    async def test_cron_calendar_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/cron calendar`` should call ``get_cron_calendar``."""
        await processor.cmd_cron("calendar")
        mock_app._client.get_cron_calendar.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cron_logs_default_limit(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/cron logs`` should call ``get_cron_logs`` and render a Table."""
        await processor.cmd_cron("logs")
        mock_app._client.get_cron_logs.assert_awaited_once()
        written = _last_written(mock_app)
        assert isinstance(written, Table)

    @pytest.mark.asyncio
    async def test_cron_logs_custom_limit(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """A numeric argument should cap the rendered rows via slicing."""
        mock_app._client.get_cron_logs.return_value = [
            {"task_name": f"t{i}", "started_at": "t", "status": "ok"} for i in range(10)
        ]
        await processor.cmd_cron("logs 3")
        mock_app._client.get_cron_logs.assert_awaited_once()
        assert isinstance(_last_written(mock_app), Table)

    @pytest.mark.asyncio
    async def test_cron_logs_invalid_limit_uses_default(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Non-numeric limits should fall back to the default of 20."""
        await processor.cmd_cron("logs abc")
        mock_app._client.get_cron_logs.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cron_unknown_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Unknown ``/cron`` subcommands should notify without hitting the API."""
        await processor.cmd_cron("bogus")
        mock_app.notify.assert_called()
        mock_app._client.get_cron_calendar.assert_not_called()
        mock_app._client.get_cron_logs.assert_not_called()

    @pytest.mark.asyncio
    async def test_cron_calendar_http_error_renders_red(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """HTTP errors from ``/cron calendar`` must surface as a red log line."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 500
        mock_app._client.get_cron_calendar.side_effect = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=response
        )
        await processor.cmd_cron("calendar")
        last = _last_written(mock_app)
        assert isinstance(last, str)
        assert "[red]" in last
        assert "500" in last


class TestConfigCommand:
    """Subcommand dispatch for ``/config``."""

    @pytest.mark.asyncio
    async def test_config_default_shows_panel(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Bare ``/config`` should call ``get_backend_config`` and render a Panel."""
        await processor.cmd_config("")
        mock_app._client.get_backend_config.assert_awaited_once()
        assert isinstance(_last_written(mock_app), Panel)

    @pytest.mark.asyncio
    async def test_config_show_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/config show`` should call ``get_backend_config``."""
        await processor.cmd_config("show")
        mock_app._client.get_backend_config.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_config_show_empty_config(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """An empty config should still render as a Panel with a friendly notice."""
        mock_app._client.get_backend_config.return_value = {}
        await processor.cmd_config("show")
        written = _last_written(mock_app)
        assert isinstance(written, Panel)

    @pytest.mark.asyncio
    async def test_config_set_updates_backend(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/config set <key> <value>`` should call ``update_backend_config``."""
        await processor.cmd_config("set backend_type ladybug")
        mock_app._client.update_backend_config.assert_awaited_once_with(
            {"backend_type": "ladybug"}
        )
        mock_app.notify.assert_called()

    @pytest.mark.asyncio
    async def test_config_set_requires_key_and_value(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/config set`` without a value should notify and not hit the API."""
        await processor.cmd_config("set backend_type")
        mock_app.notify.assert_called()
        assert "Usage" in mock_app.notify.call_args[0][0]
        mock_app._client.update_backend_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_config_set_missing_args(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/config set`` without any args should notify and not hit the API."""
        await processor.cmd_config("set")
        mock_app.notify.assert_called()
        mock_app._client.update_backend_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_config_unknown_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Unknown ``/config`` subcommands should notify with a usage hint."""
        await processor.cmd_config("bogus")
        mock_app.notify.assert_called()
        assert "Usage" in mock_app.notify.call_args[0][0]
        mock_app._client.get_backend_config.assert_not_called()
        mock_app._client.update_backend_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_config_show_http_error_renders_red(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """HTTP errors from ``/config show`` must surface as a red log line."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 500
        mock_app._client.get_backend_config.side_effect = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=response
        )
        await processor.cmd_config("show")
        last = _last_written(mock_app)
        assert isinstance(last, str)
        assert "[red]" in last
        assert "500" in last


class TestPositiveIntParser:
    """Tests for the ``_parse_positive_int`` helper used by ``/cron logs``."""

    def test_empty_returns_default(self, processor: CommandProcessor) -> None:
        """Empty input returns the provided default."""
        assert processor._parse_positive_int("", default=20) == 20

    def test_valid_int(self, processor: CommandProcessor) -> None:
        """A valid positive integer is returned as-is."""
        assert processor._parse_positive_int("5", default=20) == 5

    def test_negative_returns_default(self, processor: CommandProcessor) -> None:
        """Negative and zero values fall back to the default."""
        assert processor._parse_positive_int("-3", default=20) == 20
        assert processor._parse_positive_int("0", default=20) == 20

    def test_non_numeric_returns_default(self, processor: CommandProcessor) -> None:
        """Non-numeric strings fall back to the default."""
        assert processor._parse_positive_int("abc", default=20) == 20


class TestClientCronAndConfigMethods:
    """Smoke tests for the new AgentClient methods backing the P2 commands."""

    @pytest.mark.asyncio
    async def test_get_cron_calendar_returns_list(self, client: AgentClient) -> None:
        """``get_cron_calendar`` GETs ``/api/enhanced/cron/calendar``."""
        payload = [{"id": "task-1", "name": "Backup", "schedule": "*/5 * * * *"}]
        with patch.object(
            client._http_client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = _mock_response(payload)
            result = await client.get_cron_calendar()
            mock_get.assert_awaited_once_with(
                "http://localhost:8000/api/enhanced/cron/calendar"
            )
            assert result == payload

    @pytest.mark.asyncio
    async def test_get_cron_logs_returns_list(self, client: AgentClient) -> None:
        """``get_cron_logs`` GETs ``/api/enhanced/cron/logs``."""
        payload = [{"task_name": "Backup", "status": "success"}]
        with patch.object(
            client._http_client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = _mock_response(payload)
            result = await client.get_cron_logs()
            mock_get.assert_awaited_once_with(
                "http://localhost:8000/api/enhanced/cron/logs"
            )
            assert result == payload

    @pytest.mark.asyncio
    async def test_get_backend_config_returns_dict(self, client: AgentClient) -> None:
        """``get_backend_config`` GETs ``/api/enhanced/config/backend``."""
        payload = {"backend_type": "LadybugBackend", "env_vars": {}}
        with patch.object(
            client._http_client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = _mock_response(payload)
            result = await client.get_backend_config()
            mock_get.assert_awaited_once_with(
                "http://localhost:8000/api/enhanced/config/backend"
            )
            assert result == payload

    @pytest.mark.asyncio
    async def test_update_backend_config_puts_payload(
        self, client: AgentClient
    ) -> None:
        """``update_backend_config`` PUTs the payload at ``/config/backend``."""
        payload = {"status": "success", "message": "Restart required"}
        with patch.object(
            client._http_client, "put", new_callable=AsyncMock
        ) as mock_put:
            mock_put.return_value = _mock_response(payload)
            result = await client.update_backend_config({"backend_type": "ladybug"})
            mock_put.assert_awaited_once_with(
                "http://localhost:8000/api/enhanced/config/backend",
                json={"backend_type": "ladybug"},
            )
            assert result == payload

    @pytest.mark.asyncio
    async def test_get_cron_calendar_raises_on_error(self, client: AgentClient) -> None:
        """Non-2xx responses propagate as ``HTTPStatusError``."""
        with patch.object(
            client._http_client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = _mock_response({"detail": "fail"}, status_code=500)
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_cron_calendar()
