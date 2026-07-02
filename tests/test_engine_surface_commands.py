"""Tests for the engine-surface slash commands (W2 gateway exposure).

Covers ``/ask`` (KG-2.308), ``/nl`` (KG-2.305), ``/obs`` (PromQL + traces,
KG-2.310), ``/broker`` (KG-2.310), and ``/kvcache`` (KG-2.306/2.310) added to
surface the epistemic-graph ``/graph/*`` engine-surface routes in the TUI.

The tests drive the command handlers against a mocked ``AgentClient`` and
assert both the correct gateway call and that a renderable is emitted, so a
future refactor cannot silently drop a command's backend wiring.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_terminal_ui.commands import CommandProcessor


@pytest.fixture
def mock_app() -> MagicMock:
    """Create a mock ``AgentApp`` wired for engine-surface command tests."""
    app = MagicMock()
    app.notify = MagicMock()

    log = AsyncMock()
    app.query_one = MagicMock(return_value=log)

    app._client = AsyncMock()
    app._client.graph_ask_data = AsyncMock(
        return_value={
            "answer": "42 files.",
            "query": "SELECT count(*) FROM files",
            "rows": [{"count": 42}],
        }
    )
    app._client.graph_nl_query = AsyncMock(
        return_value={
            "query": "MATCH (n:File) RETURN n LIMIT 5",
            "dialect": "cypher",
            "rows": [{"n": "a.py"}, {"n": "b.py"}],
        }
    )
    app._client.graph_promql = AsyncMock(
        return_value={
            "surface": "promql",
            "action": "instant",
            "result": [
                {"metric": {"__name__": "up"}, "value": [1234, "1"]},
            ],
        }
    )
    app._client.graph_traces = AsyncMock(
        return_value={
            "surface": "traces",
            "result": {
                "traces": [
                    {
                        "trace_id": "abc",
                        "service": "graph-os",
                        "operation": "query",
                        "duration_ms": 12,
                    }
                ]
            },
        }
    )
    app._client.graph_broker = AsyncMock(
        return_value={"surface": "broker", "result": {"queues": 3, "messages": 7}}
    )
    app._client.graph_kvcache = AsyncMock(
        return_value={"surface": "kvcache", "result": {"entries": 10, "hits": 5}}
    )
    return app


@pytest.fixture
def processor(mock_app: MagicMock) -> CommandProcessor:
    """Create a ``CommandProcessor`` bound to the mock app."""
    return CommandProcessor(mock_app)


class TestCommandRegistration:
    """Each engine-surface command must be registered."""

    @pytest.mark.parametrize("name", ["ask", "nl", "obs", "broker", "kvcache"])
    def test_registered(self, processor: CommandProcessor, name: str) -> None:
        assert name in processor.commands


class TestAskAndNlCommands:
    """``/ask`` and ``/nl`` reach the NL-query gateway routes."""

    @pytest.mark.asyncio
    async def test_ask_calls_ask_data(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        await processor.cmd_ask("how many files?")
        mock_app._client.graph_ask_data.assert_awaited_once_with("how many files?")

    @pytest.mark.asyncio
    async def test_ask_empty_warns(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        await processor.cmd_ask("   ")
        mock_app._client.graph_ask_data.assert_not_awaited()
        mock_app.notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_nl_executes_by_default(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        await processor.cmd_nl("list files")
        mock_app._client.graph_nl_query.assert_awaited_once_with(
            "list files", execute=True
        )

    @pytest.mark.asyncio
    async def test_nl_preview_dry_runs(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        await processor.cmd_nl("preview list files")
        mock_app._client.graph_nl_query.assert_awaited_once_with(
            "list files", execute=False
        )


class TestObsCommand:
    """``/obs`` dispatches PromQL instant/range and trace search."""

    @pytest.mark.asyncio
    async def test_instant_promql(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        await processor.cmd_obs("up")
        mock_app._client.graph_promql.assert_awaited_once_with("up", action="instant")

    @pytest.mark.asyncio
    async def test_range_promql(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        await processor.cmd_obs("range rate(x[5m])")
        mock_app._client.graph_promql.assert_awaited_once()
        assert mock_app._client.graph_promql.await_args.kwargs["action"] == "range"

    @pytest.mark.asyncio
    async def test_traces_search(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        await processor.cmd_obs("traces graph-os")
        mock_app._client.graph_traces.assert_awaited_once_with(service="graph-os")


class TestBrokerAndKvcacheCommands:
    """``/broker`` and ``/kvcache`` reach the engine surface routes."""

    @pytest.mark.asyncio
    async def test_broker_default_stats(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        await processor.cmd_broker("")
        mock_app._client.graph_broker.assert_awaited_once_with(action="stats")

    @pytest.mark.asyncio
    async def test_broker_queues(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        await processor.cmd_broker("queues")
        mock_app._client.graph_broker.assert_awaited_once_with(action="list_queues")

    @pytest.mark.asyncio
    async def test_broker_unknown_warns(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        await processor.cmd_broker("bogus")
        mock_app._client.graph_broker.assert_not_awaited()
        mock_app.notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_kvcache_stats(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        await processor.cmd_kvcache("")
        mock_app._client.graph_kvcache.assert_awaited_once_with(action="stats")


class TestSurfaceErrorRendering:
    """Tool-level errors (HTTP 200 with ``error``) render without raising."""

    @pytest.mark.asyncio
    async def test_promql_error_is_rendered(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        mock_app._client.graph_promql = AsyncMock(
            return_value={"surface": "promql", "error": "no metrics surface"}
        )
        await processor.cmd_obs("up")
        rendered = mock_app.query_one.return_value.add_info.call_args[0][0]
        assert "no metrics surface" in str(rendered)


class TestSparkline:
    """The sparkline helper degrades gracefully."""

    def test_empty(self) -> None:
        assert CommandProcessor._sparkline([]) == ""

    def test_flat_series(self) -> None:
        assert CommandProcessor._sparkline([2.0, 2.0, 2.0]) == "▁▁▁"

    def test_varied_series_length(self) -> None:
        assert len(CommandProcessor._sparkline([1.0, 2.0, 3.0, 4.0])) == 4
