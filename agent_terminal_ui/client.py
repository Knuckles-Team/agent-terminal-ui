#!/usr/bin/python
"""Agent Client implementation for the terminal UI.

This module provides high-level client wrappers for interacting with the agent
server using the native Agent Communication Protocol (ACP).
"""

import contextlib
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AgentClient:
    """Standardized client for the agent-utilities ACP protocol.

    This replaces the legacy AG-UI client with a robust, native ACP implementation.
    """

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        """Initialize the ACP client.

        Args:
            base_url: The base URL of the agent server.
        """
        self.base_url: str = base_url.rstrip("/")
        # The ACP mount is typically at /acp
        self.acp_url = f"{self.base_url}/acp"
        self._http_client = httpx.AsyncClient(timeout=30.0)

    async def create_session(self) -> str:
        """Create a new ACP session."""
        response = await self._http_client.post(f"{self.acp_url}/sessions")
        response.raise_for_status()
        return response.json().get("session_id", "")

    async def send_rpc(
        self,
        session_id: str,
        method: str,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> None:
        """Send a JSON-RPC request to the ACP session.

        Args:
            session_id: Active ACP session id.
            method: JSON-RPC method name.
            params: Method params (merged with ``sessionId``).
            headers: Optional extra HTTP headers (used for multi-model
                overrides such as ``x-agent-model-id``).
        """
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": {"sessionId": session_id, **params},
            "id": 1,
        }
        response = await self._http_client.post(
            f"{self.acp_url}/rpc/{session_id}",
            json=payload,
            headers=headers or None,
        )
        response.raise_for_status()

    async def stream_events(
        self, session_id: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream SSE from back-end server."""
        async with self._http_client.stream(
            "GET", f"{self.acp_url}/stream/{session_id}"
        ) as stream:
            async for line in stream.aiter_lines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        yield event
                    except json.JSONDecodeError:
                        continue

    async def stream(
        self,
        query: str,
        session_id: str | None = None,
        parts: list[dict[str, Any]] | None = None,
        mode_id: str | None = None,
        model: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream real-time events from the ACP session.

        Args:
            query: The user prompt to send to the agent.
            session_id: Optional existing session ID to resume.
            parts: Optional list of multi-modal message parts.
            model: Optional model identifier to use for this request.

        Yields:
            Standardized ACP event dictionaries.
        """
        try:
            if not session_id:
                session_id = await self.create_session()

            # Handle mode selection
            if mode_id:
                # prioritize passed mode_id
                pass
            elif query.startswith("/plan "):
                query = query[6:]
                mode_id = "plan"
            elif query.startswith("/build "):
                query = query[7:]
                mode_id = "build"
            elif query.startswith("/chat "):
                query = query[6:]
                mode_id = "ask"
            else:
                mode_id = "ask"

            # Send the prompt as an RPC call. Include the model id as an
            # ``x-agent-model-id`` header so the backend can apply the
            # override without touching the RPC schema, but only when a
            # model is actually selected (keeps the default call shape
            # identical to the pre-multi-model behaviour).
            rpc_params = {"content": query, "modeId": mode_id, "parts": parts or []}
            if model:
                rpc_params["model"] = model
            if model:
                await self.send_rpc(
                    session_id,
                    "message/send",
                    rpc_params,
                    headers={"x-agent-model-id": model},
                )
            else:
                await self.send_rpc(
                    session_id,
                    "message/send",
                    rpc_params,
                )

            # Stream events from the session
            async for event in self.stream_events(session_id):
                # Standardize events for the TUI to consume
                event_type = event.get("type")
                if event_type == "text-delta":
                    yield {"type": "text", "content": event.get("text", "")}
                elif event_type == "text":
                    yield {"type": "text", "content": event.get("content", "")}
                elif event_type == "thinking":
                    yield {
                        "type": "sideband",
                        "data": {
                            "type": "thought",
                            "content": event.get("thought", ""),
                        },
                    }
                elif event_type == "plan-updated":
                    yield {
                        "type": "sideband",
                        "data": {"type": "plan", "plan": event.get("plan", [])},
                    }
                elif event_type == "tool-call" or event_type == "tool_call":
                    yield {
                        "type": "tool_call",
                        "data": event.get("call") or event.get("data"),
                    }
                elif event_type == "error":
                    yield {
                        "type": "error",
                        "message": event.get("message", "Unknown error"),
                    }
                elif event_type == "turn-end":
                    yield {"type": "turn_end"}
                else:
                    yield event

        except Exception as e:
            logger.exception(f"ACP Stream Error: {e}")
            yield {"type": "error", "message": str(e)}

    async def send_decision(
        self,
        decisions: dict[str, str],
        feedback: str | None = None,
        session_id: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Send tool approval decisions back to the agent.

        Args:
            decisions: decision map.
            feedback: Optional feedback for the agent.
            session_id: Optional session id.
        """
        try:
            if not session_id:
                logger.error("No session ID to send decision")
                return

            for call_id, decision in decisions.items():
                await self.send_rpc(
                    session_id,
                    "approve_tool",
                    {"call_id": call_id, "decision": decision, "feedback": feedback},
                )

            # resume streaming if needed
            async for event in self.stream_events(session_id):
                yield event
        except Exception as e:
            logger.error(f"Decision Error: {e}")
            yield {"type": "error", "message": str(e)}

    async def get_metadata(self) -> dict[str, Any]:
        """Fetch general agent metadata."""
        try:
            response = await self._http_client.get(f"{self.base_url}/a2a")
            return response.json()
        except Exception:
            return {}

    async def list_configured_models(self) -> dict[str, Any]:
        """Fetch the configured LLM model registry from the backend.

        Hits the core ``GET /models`` endpoint exposed by
        ``agent_utilities.server``. The response has the shape
        ``{"models": [...], "default_id": "..."}`` where each model is a
        serialized ``ModelDefinition`` (id, name, provider, tier, tags,
        cost, is_default, ...).

        Returns:
            The raw registry payload. On any network or parse error, an
            empty ``{"models": [], "default_id": None}`` is returned so
            callers can render a graceful empty-state.
        """
        try:
            response = await self._http_client.get(f"{self.base_url}/models")
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                return data
            return {"models": [], "default_id": None}
        except Exception as e:
            logger.error(f"Failed to fetch model registry: {e}")
            return {"models": [], "default_id": None}

    async def list_tools(self) -> list[dict[str, Any]]:
        """Fetch the loaded skills and tools from the backend Knowledge Graph.

        Hits the core ``GET /tools`` endpoint exposed by ``agent_utilities.server``.
        Returns a list of dicts representing Tool and Skill nodes.
        """
        try:
            response = await self._http_client.get(f"{self.base_url}/tools")
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"Failed to fetch tools registry: {e}")
            return []

    async def get_chat(self, chat_id: str) -> dict[str, Any]:
        """Fetch full history for a specific chat session.

        Args:
            chat_id: The unique identifier of the chat.

        Returns:
            Dictionary containing chat metadata and message history.
        """
        try:
            response = await self._http_client.get(f"{self.base_url}/chats/{chat_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch chat {chat_id}: {e}")
            return {}

    async def list_chats(self) -> list[dict[str, Any]]:
        """Fetch the list of available chat sessions.

        Returns:
            List of chat summary dictionaries.
        """
        response = await self._http_client.get(f"{self.base_url}/chats")
        response.raise_for_status()
        return response.json()

    async def get_mcp_config(self) -> dict[str, Any]:
        """Fetch MCP server configuration from the backend.

        Returns MCP config or empty default on error to prevent AttributeError.

        Returns:
            Dictionary containing MCP configuration (has ``mcpServers`` key),
            or a safe empty default when servers are not available.
        """
        try:
            response = await self._http_client.get(f"{self.base_url}/mcp/config")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.debug(f"Failed to fetch MCP config, using empty default: {e}")
            return {"servers": [], "available": False}

    async def list_mcp_tools(self) -> list[dict[str, Any]]:
        """Fetch the list of tools exposed by connected MCP servers.

        Returns tool list or empty on error to prevent AttributeError.

        Returns:
            List of MCP tool definition dictionaries with name and description.
            Empty list if no tools available or connection fails.
        """
        try:
            response = await self._http_client.get(f"{self.base_url}/mcp/tools")
            response.raise_for_status()
            return response.json().get("tools", [])
        except Exception as e:
            logger.debug(f"Failed to fetch MCP tools, returning empty list: {e}")
            return []

    async def list_skills(self) -> list[dict[str, Any]]:
        """Fetch available skills from the backend or filesystem."""
        try:
            # Try to use the helper function from agent-utilities
            logger.info(
                f"Fetching skills from {self.base_url}/api/enhanced/helpers/list_skills"
            )
            response = await self._http_client.post(
                f"{self.base_url}/api/enhanced/helpers/list_skills", json={}
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Skills response: {result}")
            # The helper returns the result directly
            if isinstance(result, list):
                return result
            elif isinstance(result, dict) and "result" in result:
                return result["result"]
            return []
        except Exception as e:
            logger.error(f"Failed to fetch skills from backend: {e}")
            # Fallback: try to load skills from universal-skills directory
            return await self._load_skills_from_filesystem()

    async def _load_skills_from_filesystem(self) -> list[dict[str, Any]]:
        """Load skills from the universal-skills directory as a fallback."""
        try:
            from pathlib import Path

            # Try to find universal-skills directory
            # Need to go up to Workspace level
            workspace_root = Path(__file__).parent.parent.parent.parent
            skills_dirs = [
                workspace_root
                / "ai"
                / "skills"
                / "universal-skills"
                / "universal_skills"
                / "skills",
                workspace_root
                / "agent-packages"
                / "skills"
                / "universal-skills"
                / "universal_skills"
                / "skills",
                Path.home() / ".codeium" / "windsurf" / "skills",
                Path.home() / ".config" / "devin" / "skills",
            ]

            skills_dir = None
            for dir_path in skills_dirs:
                if dir_path.exists() and dir_path.is_dir():
                    skills_dir = dir_path
                    logger.info(f"Found skills directory: {skills_dir}")
                    break

            if not skills_dir:
                logger.warning(
                    f"Could not find universal-skills directory in {skills_dirs}"
                )
                logger.warning(f"Workspace root: {workspace_root}")
                return []

            skills = []
            for skill_dir in skills_dir.iterdir():
                if skill_dir.is_dir():
                    skill_id = skill_dir.name
                    # Try to read SKILL.md if it exists
                    skill_md = skill_dir / "SKILL.md"
                    description = ""
                    if skill_md.exists():
                        content = skill_md.read_text(encoding="utf-8")
                        # Try to parse YAML frontmatter first
                        lines = content.split("\n")
                        in_yaml = False
                        yaml_content = []

                        for line in lines:
                            if line.strip() == "---":
                                if not in_yaml:
                                    in_yaml = True
                                else:
                                    # End of YAML frontmatter
                                    break
                            elif in_yaml:
                                yaml_content.append(line)

                        # Parse YAML for description
                        if yaml_content:
                            with contextlib.suppress(Exception):
                                # YAML parsing failed, fall back to simple parsing
                                import yaml

                                yaml_data = yaml.safe_load("\n".join(yaml_content))
                                if (
                                    isinstance(yaml_data, dict)
                                    and "description" in yaml_data
                                ):
                                    description = yaml_data["description"]

                        # If no description from YAML, try simple parsing
                        if not description:
                            for line in lines:
                                line = line.strip()
                                # Skip YAML markers and empty lines
                                if line and line != "---" and not line.startswith("#"):
                                    description = line
                                    break

                    skills.append(
                        {"id": skill_id, "name": skill_id, "description": description}
                    )

            logger.info(f"Loaded {len(skills)} skills from filesystem")
            return skills
        except Exception as e:
            logger.error(f"Failed to load skills from filesystem: {e}")
            return []

    async def get_graph_stats(self) -> dict[str, Any]:
        """Fetch aggregate statistics for the knowledge graph.

        Returns:
            Dictionary with totals and by-type breakdowns.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/graph/stats"
        )
        response.raise_for_status()
        return response.json()

    async def get_fleet_topology(self) -> dict[str, Any]:
        """Fetch the fleet worker and placement topology (OS-5.10).

        Returns:
            Dictionary describing fleet workers and their placement.
        """
        response = await self._http_client.get(f"{self.base_url}/api/fleet/topology")
        response.raise_for_status()
        return response.json()

    async def get_fleet_approvals(self) -> list[dict[str, Any]]:
        """Fetch pending ActionPolicy approvals awaiting a decision (OS-5.24).

        Returns:
            List of pending approval dictionaries.
        """
        response = await self._http_client.get(f"{self.base_url}/api/fleet/approvals")
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            return data.get("approvals", [])
        return data if isinstance(data, list) else []

    async def grant_fleet_approval(self, approval_id: str) -> dict[str, Any]:
        """Grant a pending fleet approval by identifier.

        Args:
            approval_id: The identifier of the approval to grant.

        Returns:
            The gateway response payload.
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/fleet/approvals/grant",
            json={"approval_id": approval_id},
        )
        response.raise_for_status()
        return response.json()

    async def list_graph_nodes(
        self, node_type: str | None = None
    ) -> list[dict[str, Any]]:
        """List graph nodes, optionally filtered by type.

        Args:
            node_type: Optional node type to filter on (e.g. ``File``, ``Symbol``).

        Returns:
            List of node dictionaries.
        """
        params: dict[str, str] = {}
        if node_type:
            params["node_type"] = node_type
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/graph/nodes", params=params
        )
        response.raise_for_status()
        return response.json()

    async def list_graph_relationships(self, limit: int = 100) -> list[dict[str, Any]]:
        """List graph relationships up to ``limit`` entries.

        Args:
            limit: Maximum number of relationships to return.

        Returns:
            List of relationship dictionaries.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/graph/relationships",
            params={"limit": limit},
        )
        response.raise_for_status()
        return response.json()

    async def search_graph(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Hybrid search across graph nodes.

        Args:
            query: Free-text search query.
            top_k: Maximum number of hits to return.

        Returns:
            List of search-hit dictionaries.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/graph/search",
            params={"query": query, "top_k": top_k},
        )
        response.raise_for_status()
        return response.json()

    async def get_graph_impact(self, symbol: str) -> list[dict[str, Any]]:
        """Return the topological impact set for ``symbol``.

        Args:
            symbol: Fully-qualified symbol name (e.g. ``module.Class.method``).

        Returns:
            List of impacted node dictionaries.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/graph/impact/{symbol}"
        )
        response.raise_for_status()
        return response.json()

    async def get_impact(self, symbol: str) -> list[dict[str, Any]]:
        """Return impact-analysis results for ``symbol``.

        Alias of :meth:`get_graph_impact` that matches the parity audit naming.

        Args:
            symbol: Fully-qualified symbol name.

        Returns:
            List of impacted node dictionaries.
        """
        return await self.get_graph_impact(symbol)

    async def reload_mcp(self) -> dict[str, Any]:
        """Hot-reload the backend MCP configuration.

        Returns:
            Dictionary with ``status`` and reload details
            (e.g. ``{"status": "reloaded", "agents": N, "tools": M}``).
        """
        response = await self._http_client.post(f"{self.base_url}/mcp/reload")
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        """Close the underlying HTTP client and release its connections."""
        await self._http_client.aclose()

    async def get_dashboard_full(self) -> dict[str, Any]:
        """Fetch the service dashboard layout and widget data in one request.

        Returns:
            ``{"layout": {...}, "data": {service_id: {...}}}`` from the backend
            gateway's ``/api/dashboard/full`` endpoint. Fetching over HTTP keeps
            the frontend free of the heavy ``agent_utilities`` gateway package.
        """
        response = await self._http_client.get(f"{self.base_url}/api/dashboard/full")
        response.raise_for_status()
        return response.json()

    async def get_dashboard_data(self) -> dict[str, Any]:
        """Fetch current widget data for all configured dashboard services.

        Returns:
            Mapping of ``service_id`` to its widget-data dictionary.
        """
        response = await self._http_client.get(f"{self.base_url}/api/dashboard/data")
        response.raise_for_status()
        return response.json()

    async def generate_codemap(self, prompt: str) -> dict[str, Any]:
        """Generate a codebase codemap artifact for ``prompt``.

        Args:
            prompt: Free-form description of the target code region.

        Returns:
            Dictionary with ``status``, ``codemap_id``, and an ``artifact``
            payload containing ``mermaid`` and/or ``markdown`` renders.
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/codemap", json={"prompt": prompt}
        )
        response.raise_for_status()
        return response.json()

    async def list_resources(self) -> list[dict[str, Any]]:
        """List callable resources exposed by the backend.

        Returns:
            List of resource dictionaries (type, name, description, ...).
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/resources"
        )
        response.raise_for_status()
        return response.json()

    async def spawn_resource(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Spawn a specialized agent from ``spec``.

        Args:
            spec: Specialized-agent payload forwarded to the backend verbatim.

        Returns:
            The spawned-agent descriptor returned by the server.
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/resources/spawn", json=spec
        )
        response.raise_for_status()
        return response.json()

    async def get_pipeline_status(self) -> dict[str, Any]:
        """Fetch the current 12-phase ingestion pipeline status.

        Returns:
            Dictionary with ``status`` and per-phase details under ``phases``.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/pipeline/status"
        )
        response.raise_for_status()
        return response.json()

    async def trigger_pipeline(self, phase: str | None = None) -> dict[str, Any]:
        """Trigger a pipeline run for ``phase`` or the full pipeline.

        Args:
            phase: Optional phase name (e.g. ``"scan"``, ``"embedding"``).

        Returns:
            Dictionary containing ``status`` and trigger metadata.
        """
        payload: dict[str, Any] = {}
        if phase:
            payload["phase"] = phase
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/pipeline/trigger", json=payload
        )
        response.raise_for_status()
        return response.json()

    async def get_maintenance_status(self) -> dict[str, Any]:
        """Fetch the current graph-maintenance status.

        Returns:
            Dictionary with ``status`` and per-operation details under
            ``operations``.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/maintenance/status"
        )
        response.raise_for_status()
        return response.json()

    async def trigger_maintenance(self, operation: str | None = None) -> dict[str, Any]:
        """Trigger a maintenance operation (e.g. ``prune``, ``reindex``).

        Args:
            operation: Optional maintenance operation name.

        Returns:
            Dictionary containing ``status`` and operation metadata.
        """
        payload: dict[str, Any] = {}
        if operation:
            payload["operation"] = operation
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/maintenance/trigger", json=payload
        )
        response.raise_for_status()
        return response.json()

    async def list_kbs(self) -> list[dict[str, Any]]:
        """List all knowledge bases.

        Returns:
            List of KB summary dictionaries.
        """
        response = await self._http_client.get(f"{self.base_url}/api/enhanced/kb/list")
        response.raise_for_status()
        return response.json()

    async def search_kb(
        self, query: str, kb_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Hybrid search across one or all knowledge bases.

        Args:
            query: Free-text search query.
            kb_id: Optional KB identifier to scope the search.

        Returns:
            List of KB-hit dictionaries.
        """
        params: dict[str, str] = {"query": query}
        if kb_id:
            params["kb_id"] = kb_id
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/kb/search", params=params
        )
        response.raise_for_status()
        return response.json()

    async def get_kb_article(self, article_id: str) -> dict[str, Any]:
        """Retrieve a KB article by id.

        Args:
            article_id: Unique article identifier.

        Returns:
            Article dictionary with full markdown content.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/kb/article/{article_id}"
        )
        response.raise_for_status()
        return response.json()

    async def ingest_kb(self, source: str, kb_name: str) -> dict[str, Any]:
        """Ingest a source (file, directory, or URL) into a knowledge base.

        Args:
            source: Path or URL to ingest.
            kb_name: Name of the target knowledge base.

        Returns:
            Ingestion status dictionary.
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/kb/ingest",
            json={"source": source, "kb_name": kb_name},
        )
        response.raise_for_status()
        return response.json()

    async def create_memory(self, memory: dict[str, Any]) -> dict[str, Any]:
        """Create a new memory node in the knowledge graph.

        Args:
            memory: Memory payload sent to the backend.

        Returns:
            The created memory dictionary as returned by the server.
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/graph/memory", json=memory
        )
        response.raise_for_status()
        return response.json()

    async def get_memory(self, memory_id: str) -> dict[str, Any]:
        """Fetch a memory node by id.

        Args:
            memory_id: Memory identifier.

        Returns:
            Memory dictionary.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/graph/memory/{memory_id}"
        )
        response.raise_for_status()
        return response.json()

    async def update_memory(
        self, memory_id: str, memory: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing memory node.

        Args:
            memory_id: Memory identifier.
            memory: New memory payload.

        Returns:
            The updated memory dictionary.
        """
        response = await self._http_client.put(
            f"{self.base_url}/api/enhanced/graph/memory/{memory_id}", json=memory
        )
        response.raise_for_status()
        return response.json()

    async def delete_memory(self, memory_id: str) -> None:
        """Delete a memory node from the knowledge graph.

        Args:
            memory_id: Memory identifier.
        """
        response = await self._http_client.delete(
            f"{self.base_url}/api/enhanced/graph/memory/{memory_id}"
        )
        response.raise_for_status()

    async def list_specs(self) -> list[dict[str, Any]]:
        """List SDD specifications.

        Returns:
            List of specification dictionaries.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/sdd/specs"
        )
        response.raise_for_status()
        return response.json()

    async def get_constitution(self) -> dict[str, Any]:
        """Fetch the current project constitution.

        Returns:
            Constitution dictionary (may be empty if not yet defined).
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/sdd/constitution"
        )
        response.raise_for_status()
        return response.json()

    async def list_plans(self) -> list[dict[str, Any]]:
        """List SDD implementation plans.

        Returns:
            List of plan dictionaries.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/sdd/plans"
        )
        response.raise_for_status()
        return response.json()

    async def get_tasks(self, plan_id: str | None = None) -> list[dict[str, Any]]:
        """List SDD tasks, optionally scoped to a single plan.

        Args:
            plan_id: Optional plan identifier to filter on.

        Returns:
            List of task dictionaries.
        """
        params: dict[str, str] = {}
        if plan_id:
            params["plan_id"] = plan_id
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/sdd/tasks", params=params
        )
        response.raise_for_status()
        return response.json()

    async def get_cron_calendar(self) -> list[dict[str, Any]]:
        """Fetch the scheduled cron task calendar.

        Returns:
            List of cron task dictionaries describing the schedule, last/next
            run timestamps, and current status.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/cron/calendar"
        )
        response.raise_for_status()
        return response.json()

    async def get_cron_logs(self) -> list[dict[str, Any]]:
        """Fetch recent cron execution logs.

        Returns:
            List of cron log dictionaries (most recent first) containing the
            task name, start time, status, and output preview.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/cron/logs"
        )
        response.raise_for_status()
        return response.json()

    async def get_backend_config(self) -> dict[str, Any]:
        """Retrieve the current backend configuration.

        Returns:
            Dictionary describing the backend type, connection settings, and
            environment overrides reported by the server.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/config/backend"
        )
        response.raise_for_status()
        return response.json()

    async def update_backend_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Update the backend configuration.

        Args:
            config: Partial or full backend configuration dictionary.

        Returns:
            The server acknowledgement payload (usually contains a status and
            restart-required message).
        """
        response = await self._http_client.put(
            f"{self.base_url}/api/enhanced/config/backend", json=config
        )
        response.raise_for_status()
        return response.json()

    # ─────────────────────────────────────────────────────────────────
    #  Prompt Management (CONCEPT:KG-002)
    # ─────────────────────────────────────────────────────────────────

    async def list_prompts(self) -> list[dict[str, Any]]:
        """List all prompts from the KG.

        CONCEPT:KG-002 — Prompt Management
        """
        response = await self._http_client.get(f"{self.base_url}/api/enhanced/prompts")
        response.raise_for_status()
        return response.json()

    async def get_prompt(self, prompt_id: str) -> dict[str, Any]:
        """Get a single prompt by ID.

        CONCEPT:KG-002 — Prompt Management
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/prompts/{prompt_id}"
        )
        response.raise_for_status()
        return response.json()

    async def create_prompt(
        self, name: str, content: str, description: str = ""
    ) -> dict[str, Any]:
        """Create a new prompt in the KG.

        CONCEPT:KG-002 — Prompt Management
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/prompts",
            json={"name": name, "content": content, "description": description},
        )
        response.raise_for_status()
        return response.json()

    async def update_prompt(self, prompt_id: str, content: str) -> dict[str, Any]:
        """Update a prompt (creates new version via SUPERSEDES).

        CONCEPT:KG-002 — Prompt Management
        """
        response = await self._http_client.put(
            f"{self.base_url}/api/enhanced/prompts/{prompt_id}",
            json={"content": content},
        )
        response.raise_for_status()
        return response.json()

    async def get_prompt_versions(self, prompt_id: str) -> list[dict[str, Any]]:
        """Get version history for a prompt.

        CONCEPT:KG-002 — Prompt Management
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/prompts/{prompt_id}/versions"
        )
        response.raise_for_status()
        return response.json()

    async def rollback_prompt(self, prompt_id: str, version_id: str) -> dict[str, Any]:
        """Rollback a prompt to a previous version.

        CONCEPT:KG-002 — Prompt Management (AHE Rollback)
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/prompts/{prompt_id}/rollback/{version_id}"
        )
        response.raise_for_status()
        return response.json()

    # ─────────────────────────────────────────────────────────────────
    #  Granular Resource Queries (CONCEPT:KG-003)
    # ─────────────────────────────────────────────────────────────────

    async def list_skills_only(self) -> list[dict[str, Any]]:
        """List skills only (no MCP tools).

        CONCEPT:KG-003 — Granular Resource Queries
        """
        response = await self._http_client.get(f"{self.base_url}/api/enhanced/skills")
        response.raise_for_status()
        return response.json()

    async def list_tools_only(self) -> list[dict[str, Any]]:
        """List MCP tools only (no skills).

        CONCEPT:KG-003 — Granular Resource Queries
        """
        response = await self._http_client.get(f"{self.base_url}/api/enhanced/tools")
        response.raise_for_status()
        return response.json()

    async def toggle_resource(self, resource_id: str) -> dict[str, Any]:
        """Toggle enabled/disabled on any skill or tool.

        CONCEPT:KG-003 — Granular Resource Queries
        """
        # Try skills first, then tools
        for resource_type in ("skills", "tools"):
            try:
                response = await self._http_client.post(
                    f"{self.base_url}/api/enhanced/{resource_type}/{resource_id}/toggle"
                )
                if response.status_code == 200:
                    return response.json()
            except Exception:
                continue  # nosec B112
        raise ValueError(f"Resource {resource_id} not found")

    async def close(self) -> None:
        """Close the client."""
        await self._http_client.aclose()


# Alias for backward compatibility and protocol-specific naming
ACPClient = AgentClient
