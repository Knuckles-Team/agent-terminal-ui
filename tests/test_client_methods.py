"""Tests for AgentClient backend-query methods.

Covers the thin HTTP wrappers around the agent server: legacy ``/chats`` and
``/mcp/*`` endpoints plus the ``/api/enhanced/*`` knowledge-graph, KB, memory,
and SDD endpoints used by the terminal-UI feature-parity commands.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agent_terminal_ui.client import AgentClient


@pytest.fixture
def client() -> AgentClient:
    """Create an AgentClient bound to a deterministic base URL."""
    return AgentClient(base_url="http://localhost:8000")


def _mock_response(payload: object, status_code: int = 200) -> MagicMock:
    """Build a MagicMock that mimics an ``httpx.Response``."""
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


@pytest.mark.asyncio
async def test_list_chats_returns_list(client: AgentClient) -> None:
    """``list_chats`` should GET ``/chats`` and return the decoded JSON list."""
    payload = [
        {"id": "chat-1", "title": "Session one"},
        {"id": "chat-2", "title": "Session two"},
    ]
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(payload)

        result = await client.list_chats()

        mock_get.assert_awaited_once_with("http://localhost:8000/chats")
        assert result == payload


@pytest.mark.asyncio
async def test_list_chats_raises_on_error(client: AgentClient) -> None:
    """Non-2xx responses from ``/chats`` should propagate as ``HTTPStatusError``."""
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response({"detail": "boom"}, status_code=500)

        with pytest.raises(httpx.HTTPStatusError):
            await client.list_chats()


@pytest.mark.asyncio
async def test_get_mcp_config_returns_dict(client: AgentClient) -> None:
    """``get_mcp_config`` should GET ``/mcp/config`` and return the JSON dict."""
    payload = {
        "mcpServers": {
            "memory": {"command": "mcp-memory", "args": []},
        }
    }
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(payload)

        result = await client.get_mcp_config()

        mock_get.assert_awaited_once_with("http://localhost:8000/mcp/config")
        assert result == payload
        assert "mcpServers" in result


@pytest.mark.asyncio
async def test_get_mcp_config_raises_on_error(client: AgentClient) -> None:
    """Non-2xx responses from ``/mcp/config`` should return graceful empty default."""
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response({"detail": "nope"}, status_code=404)

        # Should not raise - returns safe empty default instead
        result = await client.get_mcp_config()

        assert isinstance(result, dict)
        assert "servers" in result or "available" in result


@pytest.mark.asyncio
async def test_list_mcp_tools_returns_list(client: AgentClient) -> None:
    """``list_mcp_tools`` should GET ``/mcp/tools`` and return the JSON list."""
    payload = [
        {"name": "memory.save", "description": "Store a memory"},
        {"name": "memory.recall", "description": "Fetch a memory"},
    ]
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response({"tools": payload})

        result = await client.list_mcp_tools()

        mock_get.assert_awaited_once_with("http://localhost:8000/mcp/tools")
        assert result == payload


@pytest.mark.asyncio
async def test_list_mcp_tools_raises_on_error(client: AgentClient) -> None:
    """Non-2xx responses from ``/mcp/tools`` should return graceful empty default."""
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(
            {"detail": "unavailable"}, status_code=503
        )

    # Should not raise - returns safe empty list instead
    result = await client.list_mcp_tools()

    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Knowledge graph endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_graph_stats(client: AgentClient) -> None:
    """``get_graph_stats`` hits ``/api/enhanced/graph/stats`` and returns JSON."""
    payload = {"total_nodes": 12, "total_relationships": 7, "by_type": {"File": 3}}
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(payload)
        result = await client.get_graph_stats()
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/graph/stats"
        )
        assert result == payload


@pytest.mark.asyncio
async def test_list_graph_nodes_without_type(client: AgentClient) -> None:
    """``list_graph_nodes`` without type sends an empty param dict."""
    payload = [{"id": "n1", "labels": ["File"], "properties": {}}]
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(payload)
        result = await client.list_graph_nodes()
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/graph/nodes", params={}
        )
        assert result == payload


@pytest.mark.asyncio
async def test_list_graph_nodes_with_type(client: AgentClient) -> None:
    """``list_graph_nodes(node_type=...)`` forwards the filter."""
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response([])
        await client.list_graph_nodes(node_type="Memory")
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/graph/nodes",
            params={"node_type": "Memory"},
        )


@pytest.mark.asyncio
async def test_list_graph_relationships(client: AgentClient) -> None:
    """``list_graph_relationships`` forwards the ``limit`` query param."""
    payload = [{"source": "a", "type": "IMPORTS", "target": "b"}]
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(payload)
        result = await client.list_graph_relationships(limit=25)
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/graph/relationships",
            params={"limit": 25},
        )
        assert result == payload


@pytest.mark.asyncio
async def test_search_graph(client: AgentClient) -> None:
    """``search_graph`` hits ``/api/enhanced/graph/search`` with query + top_k."""
    payload = [{"id": "n1", "score": 0.9}]
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(payload)
        result = await client.search_graph("auth", top_k=5)
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/graph/search",
            params={"query": "auth", "top_k": 5},
        )
        assert result == payload


@pytest.mark.asyncio
async def test_get_graph_impact(client: AgentClient) -> None:
    """``get_graph_impact`` embeds the symbol in the URL path."""
    payload = [{"id": "n1", "type": "Function"}]
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(payload)
        result = await client.get_graph_impact("pkg.mod.func")
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/graph/impact/pkg.mod.func"
        )
        assert result == payload


@pytest.mark.asyncio
async def test_get_graph_stats_raises_on_error(client: AgentClient) -> None:
    """Non-2xx responses from graph stats propagate as ``HTTPStatusError``."""
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response({"detail": "fail"}, status_code=500)
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_graph_stats()


# ---------------------------------------------------------------------------
# Knowledge base endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_kbs(client: AgentClient) -> None:
    """``list_kbs`` GETs ``/api/enhanced/kb/list``."""
    payload = [{"id": "kb-1", "name": "Docs", "article_count": 4}]
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(payload)
        result = await client.list_kbs()
        mock_get.assert_awaited_once_with("http://localhost:8000/api/enhanced/kb/list")
        assert result == payload


@pytest.mark.asyncio
async def test_search_kb_without_kb_id(client: AgentClient) -> None:
    """``search_kb`` without kb id sends only the ``query`` parameter."""
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response([])
        await client.search_kb("rag")
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/kb/search",
            params={"query": "rag"},
        )


@pytest.mark.asyncio
async def test_search_kb_with_kb_id(client: AgentClient) -> None:
    """``search_kb(kb_id=...)`` forwards the KB filter."""
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response([])
        await client.search_kb("rag", kb_id="kb-docs")
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/kb/search",
            params={"query": "rag", "kb_id": "kb-docs"},
        )


@pytest.mark.asyncio
async def test_get_kb_article(client: AgentClient) -> None:
    """``get_kb_article`` retrieves a single article by id."""
    payload = {"id": "art-1", "title": "Intro", "content": "..."}
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(payload)
        result = await client.get_kb_article("art-1")
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/kb/article/art-1"
        )
        assert result == payload


@pytest.mark.asyncio
async def test_ingest_kb(client: AgentClient) -> None:
    """``ingest_kb`` POSTs a source/kb_name payload."""
    payload = {"status": "queued", "articles": 3}
    with patch.object(client._http_client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_response(payload)
        result = await client.ingest_kb("./docs", "team-docs")
        mock_post.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/kb/ingest",
            json={"source": "./docs", "kb_name": "team-docs"},
        )
        assert result == payload


# ---------------------------------------------------------------------------
# Memory CRUD endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_memory(client: AgentClient) -> None:
    """``create_memory`` POSTs a memory payload and returns the server echo."""
    payload = {"id": "mem-1", "content": "Hello"}
    with patch.object(client._http_client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_response(payload)
        result = await client.create_memory({"content": "Hello"})
        mock_post.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/graph/memory",
            json={"content": "Hello"},
        )
        assert result == payload


@pytest.mark.asyncio
async def test_get_memory(client: AgentClient) -> None:
    """``get_memory`` GETs the memory by id."""
    payload = {"id": "mem-1", "content": "Hello"}
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(payload)
        result = await client.get_memory("mem-1")
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/graph/memory/mem-1"
        )
        assert result == payload


@pytest.mark.asyncio
async def test_update_memory(client: AgentClient) -> None:
    """``update_memory`` PUTs the memory payload at ``/graph/memory/{id}``."""
    payload = {"id": "mem-1", "content": "Updated"}
    with patch.object(client._http_client, "put", new_callable=AsyncMock) as mock_put:
        mock_put.return_value = _mock_response(payload)
        result = await client.update_memory("mem-1", {"content": "Updated"})
        mock_put.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/graph/memory/mem-1",
            json={"content": "Updated"},
        )
        assert result == payload


@pytest.mark.asyncio
async def test_delete_memory(client: AgentClient) -> None:
    """``delete_memory`` DELETEs the memory and returns None."""
    with patch.object(
        client._http_client, "delete", new_callable=AsyncMock
    ) as mock_delete:
        mock_delete.return_value = _mock_response(None)
        await client.delete_memory("mem-1")
        mock_delete.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/graph/memory/mem-1"
        )


# ---------------------------------------------------------------------------
# SDD endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_specs(client: AgentClient) -> None:
    """``list_specs`` GETs ``/api/enhanced/sdd/specs``."""
    payload = [{"id": "spec-1", "title": "Auth"}]
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(payload)
        result = await client.list_specs()
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/sdd/specs"
        )
        assert result == payload


@pytest.mark.asyncio
async def test_get_constitution(client: AgentClient) -> None:
    """``get_constitution`` GETs the project constitution."""
    payload = {"governance_rules": ["TDD"], "tech_stack": {}, "quality_gates": []}
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(payload)
        result = await client.get_constitution()
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/sdd/constitution"
        )
        assert result == payload


@pytest.mark.asyncio
async def test_list_plans(client: AgentClient) -> None:
    """``list_plans`` GETs ``/api/enhanced/sdd/plans``."""
    payload = [{"id": "plan-1", "spec_id": "spec-1"}]
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(payload)
        result = await client.list_plans()
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/sdd/plans"
        )
        assert result == payload


@pytest.mark.asyncio
async def test_get_tasks_without_plan(client: AgentClient) -> None:
    """``get_tasks`` without plan id sends an empty param dict."""
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response([])
        await client.get_tasks()
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/sdd/tasks", params={}
        )


@pytest.mark.asyncio
async def test_get_tasks_with_plan(client: AgentClient) -> None:
    """``get_tasks(plan_id=...)`` forwards the filter."""
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response([])
        await client.get_tasks(plan_id="plan-1")
        mock_get.assert_awaited_once_with(
            "http://localhost:8000/api/enhanced/sdd/tasks",
            params={"plan_id": "plan-1"},
        )


@pytest.mark.asyncio
async def test_get_fleet_topology(client: AgentClient) -> None:
    """``get_fleet_topology`` GETs ``/api/fleet/topology`` and returns the JSON."""
    payload = {"workers": [{"host": "r820"}], "replicas": 3}
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(payload)

        result = await client.get_fleet_topology()

        mock_get.assert_awaited_once_with("http://localhost:8000/api/fleet/topology")
        assert result == payload


@pytest.mark.asyncio
async def test_get_fleet_approvals_unwraps_dict_envelope(client: AgentClient) -> None:
    """``get_fleet_approvals`` returns the ``approvals`` list from a dict envelope."""
    with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response({"approvals": [{"id": "a1"}]})

        result = await client.get_fleet_approvals()

        assert result == [{"id": "a1"}]


@pytest.mark.asyncio
async def test_grant_fleet_approval_posts_id(client: AgentClient) -> None:
    """``grant_fleet_approval`` POSTs the approval id to the grant endpoint."""
    with patch.object(client._http_client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_response({"granted": "a1"})

        result = await client.grant_fleet_approval("a1")

        mock_post.assert_awaited_once_with(
            "http://localhost:8000/api/fleet/approvals/grant",
            json={"approval_id": "a1"},
        )
        assert result == {"granted": "a1"}
