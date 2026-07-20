"""Tests for the terminal-UI feature-parity slash commands.

Covers the subcommand dispatch logic of ``/graph``, ``/kb``, ``/memory``
(direct CRUD), and ``/sdd`` added for P1-3..P1-6 of the feature parity audit.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from rich.table import Table

from agent_terminal_ui.commands import CommandProcessor


@pytest.fixture
def mock_app() -> MagicMock:
    """Create a mock ``AgentApp`` configured for parity-command tests."""
    app = MagicMock()
    app.notify = MagicMock()

    event_log = AsyncMock()
    event_log.write = MagicMock()
    event_log.clear = MagicMock()
    app.query_one = MagicMock(return_value=event_log)

    app._client = AsyncMock()
    app._client.get_graph_stats = AsyncMock(
        return_value={
            "total_nodes": 10,
            "total_relationships": 5,
            "by_type": {"File": 4, "Memory": 2},
        }
    )
    app._client.list_graph_nodes = AsyncMock(
        return_value=[
            {"id": "n1", "labels": ["File"], "properties": {"name": "a.py"}},
        ]
    )
    app._client.search_graph = AsyncMock(
        return_value=[{"id": "n1", "type": "File", "score": 0.87}]
    )
    app._client.get_graph_impact = AsyncMock(
        return_value=[{"id": "n2", "type": "Function", "name": "call_site"}]
    )

    app._client.list_kbs = AsyncMock(
        return_value=[
            {
                "id": "kb-docs",
                "name": "Docs",
                "article_count": 7,
                "health_status": "healthy",
            }
        ]
    )
    app._client.search_kb = AsyncMock(
        return_value=[
            {"id": "art-1", "title": "Intro", "kb_id": "kb-docs", "score": 0.9}
        ]
    )
    app._client.get_kb_article = AsyncMock(
        return_value={"id": "art-1", "title": "Intro", "content": "# Hello"}
    )
    app._client.ingest_kb = AsyncMock(return_value={"status": "queued"})

    app._client.create_memory = AsyncMock(
        return_value={"id": "mem-1", "content": "Hello"}
    )
    app._client.get_memory = AsyncMock(
        return_value={"id": "mem-1", "content": "Hello", "importance": 0.5}
    )
    app._client.delete_memory = AsyncMock(return_value=None)

    app._client.list_specs = AsyncMock(
        return_value=[{"id": "spec-1", "title": "Auth", "status": "draft"}]
    )
    app._client.get_constitution = AsyncMock(
        return_value={
            "governance_rules": ["TDD"],
            "tech_stack": {"lang": "python"},
            "quality_gates": ["pytest"],
        }
    )
    app._client.list_plans = AsyncMock(
        return_value=[
            {
                "id": "plan-1",
                "spec_id": "spec-1",
                "status": "in_progress",
                "technical_approach": "Use FastAPI",
            }
        ]
    )
    app._client.get_tasks = AsyncMock(
        return_value=[
            {
                "id": "task-1",
                "plan_id": "plan-1",
                "title": "Wire endpoints",
                "status": "pending",
                "parallel": True,
            }
        ]
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


class TestCommandRegistration:
    """New parity commands should be registered in ``self.commands``."""

    def test_graph_registered(self, processor: CommandProcessor) -> None:
        """``/graph`` must be exposed via the commands registry."""
        assert "graph" in processor.commands

    def test_kb_registered(self, processor: CommandProcessor) -> None:
        """``/kb`` must be exposed via the commands registry."""
        assert "kb" in processor.commands

    def test_sdd_registered(self, processor: CommandProcessor) -> None:
        """``/sdd`` must be exposed via the commands registry."""
        assert "sdd" in processor.commands

    def test_memory_still_registered(self, processor: CommandProcessor) -> None:
        """``/memory`` must remain registered after the CRUD refactor."""
        assert "memory" in processor.commands


class TestGraphCommand:
    """Subcommand dispatch for ``/graph``."""

    @pytest.mark.asyncio
    async def test_graph_default_calls_stats(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Bare ``/graph`` should invoke ``get_graph_stats``."""
        await processor.cmd_graph("")
        mock_app._client.get_graph_stats.assert_awaited_once()
        assert isinstance(_last_written(mock_app), Table)

    @pytest.mark.asyncio
    async def test_graph_stats_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/graph stats`` should invoke ``get_graph_stats``."""
        await processor.cmd_graph("stats")
        mock_app._client.get_graph_stats.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_graph_nodes_without_type(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/graph nodes`` without a filter calls ``list_graph_nodes(None)``."""
        await processor.cmd_graph("nodes")
        mock_app._client.list_graph_nodes.assert_awaited_once_with(node_type=None)

    @pytest.mark.asyncio
    async def test_graph_nodes_with_type(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/graph nodes Memory`` should forward the type filter."""
        await processor.cmd_graph("nodes Memory")
        mock_app._client.list_graph_nodes.assert_awaited_once_with(node_type="Memory")

    @pytest.mark.asyncio
    async def test_graph_search_requires_query(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/graph search`` without a query should notify the user."""
        await processor.cmd_graph("search")
        mock_app.notify.assert_called()
        assert "Usage" in mock_app.notify.call_args[0][0]
        mock_app._client.search_graph.assert_not_called()

    @pytest.mark.asyncio
    async def test_graph_search_with_query(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/graph search <query>`` should call ``search_graph``."""
        await processor.cmd_graph("search authentication")
        mock_app._client.search_graph.assert_awaited_once_with("authentication")

    @pytest.mark.asyncio
    async def test_graph_impact_requires_symbol(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/graph impact`` without a symbol notifies the user."""
        await processor.cmd_graph("impact")
        mock_app.notify.assert_called()
        mock_app._client.get_graph_impact.assert_not_called()

    @pytest.mark.asyncio
    async def test_graph_impact_with_symbol(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/graph impact <sym>`` should call ``get_graph_impact``."""
        await processor.cmd_graph("impact pkg.mod.func")
        mock_app._client.get_graph_impact.assert_awaited_once_with("pkg.mod.func")

    @pytest.mark.asyncio
    async def test_graph_unknown_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """An unknown subcommand should notify without calling any client method."""
        await processor.cmd_graph("bogus")
        mock_app.notify.assert_called()
        mock_app._client.get_graph_stats.assert_not_called()

    @pytest.mark.asyncio
    async def test_graph_http_error_renders_red(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """HTTP errors from the graph endpoint must surface as a red log line."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 500
        mock_app._client.get_graph_stats.side_effect = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=response
        )

        await processor.cmd_graph("stats")

        last = _last_written(mock_app)
        assert isinstance(last, str)
        assert "[red]" in last
        assert "500" in last


class TestKBCommand:
    """Subcommand dispatch for ``/kb``."""

    @pytest.mark.asyncio
    async def test_kb_default_lists_kbs(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Bare ``/kb`` should call ``list_kbs``."""
        await processor.cmd_kb("")
        mock_app._client.list_kbs.assert_awaited_once()
        assert isinstance(_last_written(mock_app), Table)

    @pytest.mark.asyncio
    async def test_kb_list_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/kb list`` should call ``list_kbs``."""
        await processor.cmd_kb("list")
        mock_app._client.list_kbs.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_kb_search_requires_query(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/kb search`` without a query should notify the user."""
        await processor.cmd_kb("search")
        mock_app.notify.assert_called()
        mock_app._client.search_kb.assert_not_called()

    @pytest.mark.asyncio
    async def test_kb_search_with_query(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/kb search rag`` should call ``search_kb`` without a KB id."""
        await processor.cmd_kb("search rag patterns")
        mock_app._client.search_kb.assert_awaited_once_with("rag patterns", kb_id=None)

    @pytest.mark.asyncio
    async def test_kb_search_with_kb_flag(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/kb search --kb <id> <q>`` must pass the KB id to ``search_kb``."""
        await processor.cmd_kb("search rag --kb kb-docs")
        mock_app._client.search_kb.assert_awaited_once_with("rag", kb_id="kb-docs")

    @pytest.mark.asyncio
    async def test_kb_article_requires_id(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/kb article`` without an id should notify."""
        await processor.cmd_kb("article")
        mock_app.notify.assert_called()
        mock_app._client.get_kb_article.assert_not_called()

    @pytest.mark.asyncio
    async def test_kb_article_with_id(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/kb article <id>`` should render the article content in the log."""
        await processor.cmd_kb("article art-1")
        mock_app._client.get_kb_article.assert_awaited_once_with("art-1")
        written = _last_written(mock_app)
        assert isinstance(written, str)
        assert "Intro" in written
        assert "# Hello" in written

    @pytest.mark.asyncio
    async def test_kb_ingest_requires_two_args(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/kb ingest <source>`` without a kb name should notify."""
        await processor.cmd_kb("ingest ./docs")
        mock_app.notify.assert_called()
        mock_app._client.ingest_kb.assert_not_called()

    @pytest.mark.asyncio
    async def test_kb_ingest_with_source_and_name(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/kb ingest <source> <name>`` should call ``ingest_kb``."""
        await processor.cmd_kb("ingest ./docs team-docs")
        mock_app._client.ingest_kb.assert_awaited_once_with("./docs", "team-docs")

    @pytest.mark.asyncio
    async def test_kb_unknown_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """An unknown subcommand should notify without hitting the client."""
        await processor.cmd_kb("bogus")
        mock_app.notify.assert_called()
        mock_app._client.list_kbs.assert_not_called()


class TestMemoryCommand:
    """Subcommand dispatch for the enhanced ``/memory`` command."""

    @pytest.mark.asyncio
    async def test_memory_default_lists(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Bare ``/memory`` should list memory nodes via the graph client."""
        await processor.cmd_memory("")
        mock_app._client.list_graph_nodes.assert_awaited_once_with(node_type="Memory")
        assert isinstance(_last_written(mock_app), Table)

    @pytest.mark.asyncio
    async def test_memory_list_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/memory list`` should list memory nodes."""
        await processor.cmd_memory("list")
        mock_app._client.list_graph_nodes.assert_awaited_once_with(node_type="Memory")

    @pytest.mark.asyncio
    async def test_memory_add_requires_content(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/memory add`` without content should notify."""
        await processor.cmd_memory("add")
        mock_app.notify.assert_called()
        mock_app._client.create_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_add_creates_node(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/memory add <content>`` should call ``create_memory``."""
        await processor.cmd_memory("add Remember this fact")
        mock_app._client.create_memory.assert_awaited_once_with(
            {"content": "Remember this fact"}
        )
        mock_app.notify.assert_called()

    @pytest.mark.asyncio
    async def test_memory_get(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/memory get <id>`` should fetch and render the memory."""
        await processor.cmd_memory("get mem-1")
        mock_app._client.get_memory.assert_awaited_once_with("mem-1")
        assert isinstance(_last_written(mock_app), Table)

    @pytest.mark.asyncio
    async def test_memory_delete(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/memory delete <id>`` should call ``delete_memory`` and notify."""
        await processor.cmd_memory("delete mem-1")
        mock_app._client.delete_memory.assert_awaited_once_with("mem-1")
        mock_app.notify.assert_called()
        assert "deleted" in mock_app.notify.call_args[0][0].lower(), (
            "Delete notification must mention deletion"
        )

    @pytest.mark.asyncio
    async def test_memory_search(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/memory search <query>`` should reuse ``search_graph``."""
        await processor.cmd_memory("search auth")
        mock_app._client.search_graph.assert_awaited_once_with("auth")

    @pytest.mark.asyncio
    async def test_memory_review_falls_back_to_agent(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/memory review`` should submit an agent prompt."""
        await processor.cmd_memory("review")
        mock_app.on_input_text_area_submitted.assert_awaited()
        submitted = mock_app.on_input_text_area_submitted.call_args[0][0].value
        assert "memories" in submitted.lower()

    @pytest.mark.asyncio
    async def test_memory_unknown_subcommand_falls_back_to_agent(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Unknown subcommands must preserve the old agent-driven behavior."""
        await processor.cmd_memory("sync AGENTS.md")
        mock_app.on_input_text_area_submitted.assert_awaited()
        submitted = mock_app.on_input_text_area_submitted.call_args[0][0].value
        assert "sync" in submitted.lower()


class TestSDDCommand:
    """Subcommand dispatch for ``/sdd``."""

    @pytest.mark.asyncio
    async def test_sdd_constitution_present(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/sdd constitution`` with data should render a Rich table."""
        await processor.cmd_sdd("constitution")
        mock_app._client.get_constitution.assert_awaited_once()
        assert isinstance(_last_written(mock_app), Table)

    @pytest.mark.asyncio
    async def test_sdd_constitution_empty(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/sdd constitution`` with no data should show a friendly notice."""
        mock_app._client.get_constitution.return_value = {}
        await processor.cmd_sdd("constitution")
        written = _last_written(mock_app)
        assert isinstance(written, str)
        assert "No constitution" in written

    @pytest.mark.asyncio
    async def test_sdd_specs(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/sdd specs`` should call ``list_specs``."""
        await processor.cmd_sdd("specs")
        mock_app._client.list_specs.assert_awaited_once()
        assert isinstance(_last_written(mock_app), Table)

    @pytest.mark.asyncio
    async def test_sdd_plans(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/sdd plans`` should call ``list_plans``."""
        await processor.cmd_sdd("plans")
        mock_app._client.list_plans.assert_awaited_once()
        assert isinstance(_last_written(mock_app), Table)

    @pytest.mark.asyncio
    async def test_sdd_tasks_without_plan(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/sdd tasks`` without a plan id should call ``get_tasks(None)``."""
        await processor.cmd_sdd("tasks")
        mock_app._client.get_tasks.assert_awaited_once_with(plan_id=None)

    @pytest.mark.asyncio
    async def test_sdd_tasks_with_plan(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/sdd tasks <plan_id>`` should forward the plan filter."""
        await processor.cmd_sdd("tasks plan-1")
        mock_app._client.get_tasks.assert_awaited_once_with(plan_id="plan-1")

    @pytest.mark.asyncio
    async def test_sdd_tasks_unwraps_dict(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """``/sdd tasks`` must accept ``{"tasks": [...]}`` wrappers."""
        mock_app._client.get_tasks.return_value = {
            "tasks": [
                {
                    "id": "t2",
                    "plan_id": "plan-1",
                    "title": "Write tests",
                    "status": "pending",
                    "parallel": False,
                }
            ]
        }
        await processor.cmd_sdd("tasks plan-1")
        assert isinstance(_last_written(mock_app), Table)

    @pytest.mark.asyncio
    async def test_sdd_unknown_subcommand(
        self, processor: CommandProcessor, mock_app: MagicMock
    ) -> None:
        """Unknown ``/sdd`` subcommands must notify with a usage hint."""
        await processor.cmd_sdd("")
        mock_app.notify.assert_called()
        assert "Usage" in mock_app.notify.call_args[0][0]


class TestSubcommandParser:
    """Tests for the ``_parse_subcommand`` helper used by all parity commands."""

    def test_empty_args(self, processor: CommandProcessor) -> None:
        """Empty args return empty strings."""
        assert processor._parse_subcommand("") == ("", "")

    def test_whitespace_only(self, processor: CommandProcessor) -> None:
        """Whitespace-only args return empty strings."""
        assert processor._parse_subcommand("   ") == ("", "")

    def test_single_token(self, processor: CommandProcessor) -> None:
        """A single token is returned as the subcommand with empty remainder."""
        assert processor._parse_subcommand("list") == ("list", "")

    def test_subcommand_and_rest(self, processor: CommandProcessor) -> None:
        """Subcommand + remainder are split at the first whitespace boundary."""
        assert processor._parse_subcommand("search foo bar") == (
            "search",
            "foo bar",
        )

    def test_case_insensitive_subcommand(self, processor: CommandProcessor) -> None:
        """Subcommand token is lower-cased."""
        assert processor._parse_subcommand("SEARCH Foo") == ("search", "Foo")


class TestKBFlagParser:
    """Tests for the ``_split_kb_flag`` helper used by ``/kb search``."""

    def test_no_flag(self, processor: CommandProcessor) -> None:
        """Without ``--kb`` the full string is returned as the query."""
        assert processor._split_kb_flag("rag patterns") == (
            "rag patterns",
            None,
        )

    def test_flag_at_end(self, processor: CommandProcessor) -> None:
        """``--kb`` at the end should bind to the next token."""
        assert processor._split_kb_flag("rag --kb kb-docs") == (
            "rag",
            "kb-docs",
        )

    def test_flag_at_start(self, processor: CommandProcessor) -> None:
        """``--kb`` at the start should still be parsed."""
        assert processor._split_kb_flag("--kb kb-docs rag") == (
            "rag",
            "kb-docs",
        )

    def test_flag_without_value(self, processor: CommandProcessor) -> None:
        """A trailing ``--kb`` without a value should be ignored."""
        assert processor._split_kb_flag("rag --kb") == ("rag --kb", None)
