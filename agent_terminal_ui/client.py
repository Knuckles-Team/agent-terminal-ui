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
from urllib.parse import quote

import httpx

from agent_terminal_ui.capabilities import (
    CapabilityCatalog,
    CapabilityDescriptor,
    CapabilityInvocation,
    CapabilityPreflight,
    RunCatalog,
    RunEventPage,
    RunSummary,
)

logger = logging.getLogger(__name__)

#: Prefix the gateway mounts the canonical Knowledge-Graph REST table under
#: (``agent_utilities.gateway.graph_api.register_graph_routes(app,
#: prefix="/api")``). The ``/graph/*`` action twins live there, unlike the
#: server's own un-prefixed routers (``/models``, ``/chats``, ``/tools``,
#: ``/mcp/*``).
GATEWAY_API_PREFIX = "/api"


class AgentClient:
    """Standardized wire client for the agent-utilities ACP protocol.

    The TUI treats this class as its protocol adapter: callers consume one
    normalized event vocabulary regardless of whether events originated from an
    initial turn or an approval-resume stream.  The currently shipped adapter
    speaks ACP; the application-level ``ENABLE_ACP`` compatibility switch must
    therefore select this initialized adapter rather than constructing a second,
    deferred client.
    """

    protocol = "acp"

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        """Initialize the ACP client.

        Args:
            base_url: The base URL of the agent server.
        """
        self.base_url: str = base_url.rstrip("/")
        # The ACP mount is typically at /acp
        self.acp_url = f"{self.base_url}/acp"
        self._http_client = httpx.AsyncClient(timeout=30.0)
        self._current_session_id: str | None = None

    @property
    def current_session_id(self) -> str | None:
        """Return the session most recently created or used by this client."""
        return self._current_session_id

    async def create_session(self) -> str:
        """Create a new ACP session."""
        response = await self._http_client.post(f"{self.acp_url}/sessions")
        response.raise_for_status()
        payload = response.json()
        session_id = payload.get("session_id") or payload.get("sessionId", "")
        if session_id:
            self._current_session_id = session_id
        return session_id

    @staticmethod
    def _normalize_event(event: dict[str, Any], session_id: str) -> dict[str, Any]:
        """Normalize one ACP event into the event vocabulary used by every UI.

        Keeping this translation in the transport adapter prevents initial turns
        and approval-resume turns from producing subtly different event names.
        Every normalized event carries its owning session id so consumers can
        persist, export, and resume the same conversation.
        """
        event_type = event.get("type")

        if event_type in ("text-delta", "text_delta"):
            normalized: dict[str, Any] = {
                "type": "text_delta",
                "content": event.get("delta")
                or event.get("text")
                or event.get("content", ""),
            }
        elif event_type == "text":
            normalized = {"type": "text", "content": event.get("content", "")}
        elif event_type == "thinking":
            normalized = {
                "type": "sideband",
                "data": {
                    "type": "thought",
                    "content": event.get("thought", ""),
                },
            }
        elif event_type in ("plan-updated", "plan_updated"):
            normalized = {
                "type": "sideband",
                "data": {"type": "plan", "plan": event.get("plan", [])},
            }
        elif event_type in ("tool-call", "tool_call"):
            normalized = {
                "type": "tool_call",
                "data": event.get("call") or event.get("data") or {},
            }
        elif event_type in ("tool-output", "tool_output"):
            output_data = event.get("data")
            if not isinstance(output_data, dict):
                output_data = {
                    key: value for key, value in event.items() if key != "type"
                }
            normalized = {
                "type": "tool_output",
                "data": output_data,
            }
        elif event_type == "error":
            normalized = {
                "type": "error",
                "message": event.get("message", "Unknown error"),
            }
        elif event_type in ("turn-end", "turn_end"):
            normalized = {"type": "turn_end"}
            if event.get("usage") is not None:
                normalized["usage"] = event["usage"]
        elif event_type == "usage":
            normalized = {
                "type": "usage",
                "data": event.get("usage") or event.get("data") or {},
            }
        elif event_type in ("session-started", "session_started"):
            normalized = {"type": "session_started"}
        else:
            normalized = dict(event)

        event_metadata = event.get("_event")
        if isinstance(event_metadata, dict):
            normalized.setdefault("_event", event_metadata)
            run_id = event_metadata.get("run_id")
            if run_id:
                normalized.setdefault("run_id", run_id)
        if event.get("run_id"):
            normalized.setdefault("run_id", event["run_id"])
        normalized.setdefault("session_id", session_id)
        return normalized

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

    async def submit_extraction(
        self, *, text: str = "", url: str = "", rounds: int = 1, dedup: bool = True
    ) -> dict[str, Any]:
        """Submit a document fact-extraction job to the gateway (ECO-4.43)."""
        resp = await self._http_client.post(
            f"{self.base_url}/api/enhanced/extract/submit",
            json={"text": text, "url": url, "rounds": rounds, "dedup": dedup},
        )
        resp.raise_for_status()
        return resp.json()

    async def stream_extraction(
        self, job_id: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a job's extraction events (round_start|fact|…|job_done)."""
        async with self._http_client.stream(
            "GET",
            f"{self.base_url}/api/enhanced/extract/stream/{job_id}",
            timeout=None,
        ) as stream:
            async for line in stream.aiter_lines():
                if line.startswith("data: "):
                    try:
                        yield json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

    async def extraction_jsonl(self, job_id: str) -> str:
        """Fetch a job's facts as JSONL text (upstream parity)."""
        resp = await self._http_client.get(
            f"{self.base_url}/api/enhanced/extract/jsonl/{job_id}"
        )
        resp.raise_for_status()
        return resp.text

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
            self._current_session_id = session_id

            # Surface identity before any response event.  This is deliberately
            # an event rather than an out-of-band mutable property so interactive
            # and headless consumers observe the same session contract.
            yield {"type": "session_started", "session_id": session_id}

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
                yield self._normalize_event(event, session_id)

        except Exception as e:
            logger.exception(f"ACP Stream Error: {e}")
            error = {"type": "error", "message": str(e)}
            if session_id:
                error["session_id"] = session_id
            yield error

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
            session_id = session_id or self._current_session_id
            if not session_id:
                logger.error("No session ID to send decision")
                return
            self._current_session_id = session_id

            for call_id, decision in decisions.items():
                await self.send_rpc(
                    session_id,
                    "approve_tool",
                    {"call_id": call_id, "decision": decision, "feedback": feedback},
                )

            # resume streaming if needed
            async for event in self.stream_events(session_id):
                yield self._normalize_event(event, session_id)
        except Exception as e:
            logger.error(f"Decision Error: {e}")
            error = {"type": "error", "message": str(e)}
            if session_id:
                error["session_id"] = session_id
            yield error

    async def get_metadata(self) -> dict[str, Any]:
        """Fetch general agent metadata."""
        try:
            response = await self._http_client.get(f"{self.base_url}/a2a")
            return response.json()
        except Exception:
            return {}

    @staticmethod
    def _gateway_body(response: httpx.Response) -> Any:
        """Return a direct FastAPI body or unwrap the shared HTTP envelope."""
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and "status_code" in payload and "data" in payload:
            return payload["data"]
        return payload

    async def list_capabilities(
        self,
        *,
        query: str | None = None,
        status: str | None = None,
        intent: str | None = None,
        tag: str | None = None,
        include_actions: bool = True,
    ) -> CapabilityCatalog:
        """Fetch the live catalog used by schema-driven frontend surfaces."""
        params = {
            key: value
            for key, value in {
                "q": query,
                "status": status,
                "intent": intent,
                "tag": tag,
                "include_actions": str(include_actions).lower(),
            }.items()
            if value is not None
        }
        response = await self._http_client.get(
            f"{self.base_url}/api/capabilities", params=params
        )
        return CapabilityCatalog.from_payload(self._gateway_body(response))

    async def get_capability(self, capability_id: str) -> CapabilityDescriptor:
        """Fetch one live capability descriptor by stable ID."""
        encoded = quote(capability_id, safe="")
        response = await self._http_client.get(
            f"{self.base_url}/api/capabilities/{encoded}"
        )
        return CapabilityDescriptor.from_payload(self._gateway_body(response))

    async def preflight_capability(
        self,
        capability_id: str,
        *,
        action: str | None = None,
        inputs: dict[str, Any] | None = None,
        target: str | None = None,
    ) -> CapabilityPreflight:
        """Validate inputs and preview availability/policy without executing."""
        encoded = quote(capability_id, safe="")
        response = await self._http_client.post(
            f"{self.base_url}/api/capabilities/{encoded}/preflight",
            json={
                "action": action,
                "inputs": inputs or {},
                "target": target,
            },
        )
        return CapabilityPreflight.from_payload(self._gateway_body(response))

    async def invoke_capability(
        self,
        capability_id: str,
        inputs: dict[str, Any],
        *,
        action: str,
        target: str | None = None,
        approval_id: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> CapabilityInvocation:
        """Execute or resume through the gateway-owned governance boundary."""
        encoded = quote(capability_id, safe="")
        payload: dict[str, Any] = {"action": action, "inputs": inputs}
        payload.update(
            {
                key: value
                for key, value in {
                    "target": target,
                    "approval_id": approval_id,
                    "run_id": run_id,
                    "session_id": session_id,
                }.items()
                if value is not None
            }
        )
        response = await self._http_client.post(
            f"{self.base_url}/api/capabilities/{encoded}/invoke", json=payload
        )
        result = self._gateway_body(response)
        return CapabilityInvocation.from_payload(
            capability_id,
            result,
            http_status=response.status_code,
            requested_session_id=session_id,
        )

    async def get_run_summary(self, run_id: str) -> RunSummary:
        """Fetch a summary for one replayable canonical run."""
        encoded = quote(run_id, safe="")
        response = await self._http_client.get(f"{self.base_url}/api/runs/{encoded}")
        return RunSummary.from_payload(self._gateway_body(response))

    async def list_runs(
        self,
        *,
        session_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> RunCatalog:
        """List newest-first canonical run lifecycle summaries."""
        params = {
            key: value
            for key, value in {
                "session_id": session_id,
                "status": status,
                "limit": limit,
            }.items()
            if value is not None
        }
        response = await self._http_client.get(
            f"{self.base_url}/api/runs", params=params
        )
        return RunCatalog.from_payload(self._gateway_body(response))

    async def get_run_events(
        self, run_id: str, *, after: int = 0, limit: int = 1_000
    ) -> RunEventPage:
        """Replay canonical run events after a per-run sequence cursor."""
        encoded = quote(run_id, safe="")
        response = await self._http_client.get(
            f"{self.base_url}/api/runs/{encoded}/events",
            params={"after": after, "limit": limit},
        )
        return RunEventPage.from_payload(self._gateway_body(response))

    async def get_event_schema(self) -> dict[str, Any]:
        """Fetch the versioned canonical run-event JSON Schema."""
        response = await self._http_client.get(f"{self.base_url}/api/events/schema")
        payload = self._gateway_body(response)
        return payload if isinstance(payload, dict) else {}

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

    async def _obs_get(self, path: str, params: dict | None = None) -> Any:
        """GET an /api/observability/* endpoint.

        CONCEPT:AU-ECO.mcp.usage-cost-observability-surface
        """
        try:
            response = await self._http_client.get(
                f"{self.base_url}/api/observability{path}",
                params={k: v for k, v in (params or {}).items() if v},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.debug(f"observability {path} failed: {e}")
            return None

    async def get_usage_summary(self, **f: Any) -> dict[str, Any]:
        return await self._obs_get("/summary", f) or {}

    async def get_usage_by_model(self, **f: Any) -> list[dict[str, Any]]:
        return await self._obs_get("/by-model", f) or []

    async def get_usage_tools(self, **f: Any) -> list[dict[str, Any]]:
        return await self._obs_get("/analytics/tools", f) or []

    async def get_usage_activity(self, **f: Any) -> list[dict[str, Any]]:
        return await self._obs_get("/analytics/activity", f) or []

    async def get_usage_top_sessions(
        self, *, limit: int = 20, **f: Any
    ) -> list[dict[str, Any]]:
        return await self._obs_get("/top-sessions", {"limit": limit, **f}) or []

    async def get_usage_traces(self) -> dict[str, Any]:
        return await self._obs_get("/traces") or {"enabled": False, "traces": []}

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
            # The gateway contract names this collection ``pending``. Keep the
            # legacy envelope as a read-only fallback for older deployments.
            pending = data.get("pending", data.get("approvals", []))
            return pending if isinstance(pending, list) else []
        return data if isinstance(data, list) else []

    async def grant_fleet_approval(
        self, job_id: str, decision: str = "approved"
    ) -> dict[str, Any]:
        """Resolve a pending fleet approval for a job.

        Args:
            job_id: The identifier of the fleet job awaiting approval.
            decision: Either ``"approved"`` or ``"denied"``.

        Returns:
            The gateway response payload.

        Raises:
            ValueError: If *decision* is not supported by the gateway contract.
        """
        if decision not in {"approved", "denied"}:
            msg = "decision must be 'approved' or 'denied'"
            raise ValueError(msg)

        response = await self._http_client.post(
            f"{self.base_url}/api/fleet/approvals/grant",
            json={"job_id": job_id, "decision": decision},
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

    async def query_graph_as_of(self, query: str) -> list[dict[str, Any]]:
        """Execute a (UQL) graph query verbatim, returning result rows.

        Thin pass-through to ``POST /api/enhanced/graph/query`` used by the
        temporal scrubber, which appends the engine's ``|> AS OF @<ts>``
        bi-temporal operator (KG-2.250) to the query string client-side. The
        backend passes the query through to the engine unchanged.

        Args:
            query: The full UQL query string (already carrying any AS OF suffix).

        Returns:
            List of result-row dictionaries.
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/graph/query",
            json={"query": query},
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

    async def _graph_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to a gateway ``/graph/*`` engine-surface route and unwrap it.

        The action-routed twins in :data:`ACTION_TOOL_ROUTES` (KG-2.310)
        respond with ``{"status": "success", "result": <tool-json>}``; this
        helper returns the inner ``result`` object. Tool-level failures degrade
        cleanly into ``result`` as ``{"error": "..."}`` (HTTP 200), while
        transport/gateway failures raise ``httpx.HTTPStatusError`` for the
        caller to render.

        The gateway mounts the whole canonical KG route table under ``/api``
        (``register_graph_routes(app, prefix="/api")``), so the request URL is
        ``{base_url}/api{path}``. Posting to the bare ``{base_url}{path}`` — as
        this helper used to — reached nothing: every engine-surface command
        (``/ask``, ``/nl``, ``/obs``, ``/broker``, ``/kvcache``) 404'd.

        Args:
            path: A ``/graph/*`` route path (e.g. ``/graph/promql``).
            payload: The tool keyword arguments to send as the JSON body.

        Returns:
            The unwrapped ``result`` object (empty dict when absent).
        """
        response = await self._http_client.post(
            f"{self.base_url}{GATEWAY_API_PREFIX}{path}", json=payload
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            result = data.get("result", data)
            return result if isinstance(result, dict) else {"result": result}
        return {}

    async def graph_nl_query(
        self,
        text: str,
        *,
        dialect: str = "auto",
        execute: bool = True,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Translate a natural-language request into a query (KG-2.305).

        Hits ``POST /graph/nl-query``; the AU fleet LLM plans a single
        read-only query (UQL/cypher/sql/sparql), which the engine executes.

        Returns:
            The tool payload: generated ``query``, ``rows``/``result``,
            ``citations``, or ``error``.
        """
        return await self._graph_post(
            "/graph/nl-query",
            {
                "text": text,
                "dialect": dialect,
                "execute": execute,
                "limit": limit,
            },
        )

    async def graph_ask_data(
        self,
        question: str,
        *,
        dialect: str = "auto",
        max_corrections: int = 2,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Answer a data question with the multi-step analyst loop (KG-2.308).

        Hits ``POST /graph/ask-data``; a bounded ReAct agent schema-links,
        plans, executes, self-corrects, then synthesizes a NL answer.

        Returns:
            The tool payload: synthesized ``answer``, ``query``, result rows,
            ``citations``, ``schema``, attempt trace, or ``error``.
        """
        return await self._graph_post(
            "/graph/ask-data",
            {
                "question": question,
                "dialect": dialect,
                "max_corrections": max_corrections,
                "limit": limit,
            },
        )

    async def graph_promql(
        self,
        query: str,
        *,
        action: str = "instant",
        time: str = "",
        start: str = "",
        end: str = "",
        step: str = "",
    ) -> dict[str, Any]:
        """Query engine observability metrics with PromQL (KG-2.310).

        Hits ``POST /graph/promql``; ``action='instant'`` evaluates once,
        ``action='range'`` evaluates over ``start..end`` at ``step``.

        Returns:
            The tool payload (metric samples under ``result``) or ``error``.
        """
        payload: dict[str, Any] = {"query": query, "action": action}
        for key, value in (
            ("time", time),
            ("start", start),
            ("end", end),
            ("step", step),
        ):
            if value:
                payload[key] = value
        return await self._graph_post("/graph/promql", payload)

    async def graph_traces(
        self,
        *,
        action: str = "search",
        trace_id: str = "",
        service: str = "",
        operation: str = "",
        query: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search or fetch distributed traces (KG-2.310).

        Hits ``POST /graph/traces``; ``action='search'`` filters by
        ``service``/``operation``/``query``, ``action='get'`` fetches one
        ``trace_id``.

        Returns:
            The tool payload (matched traces under ``result``) or ``error``.
        """
        payload: dict[str, Any] = {"action": action, "limit": limit}
        for key, value in (
            ("trace_id", trace_id),
            ("service", service),
            ("operation", operation),
            ("query", query),
        ):
            if value:
                payload[key] = value
        return await self._graph_post("/graph/traces", payload)

    async def graph_broker(
        self, *, action: str = "stats", params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Inspect the engine message broker (KG-2.310).

        Hits ``POST /graph/broker``; ``action`` is a broker method such as
        ``stats``, ``list_queues``, or ``list_exchanges``. Extra keyword
        arguments are forwarded via ``params_json``.

        Returns:
            The tool payload (broker stats/listing under ``result``) or
            ``error``.
        """
        payload: dict[str, Any] = {"action": action}
        if params:
            payload["params_json"] = json.dumps(params)
        return await self._graph_post("/graph/broker", payload)

    async def graph_kvcache(self, *, action: str = "stats") -> dict[str, Any]:
        """Read shared content-addressed KV-cache stats (KG-2.306/2.310).

        Hits ``POST /graph/kvcache``; ``action='stats'`` returns occupancy and
        dedup counters.

        Returns:
            The tool payload (cache stats under ``result``) or ``error``.
        """
        return await self._graph_post("/graph/kvcache", {"action": action})

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
    #  Prompt Management (CONCEPT:TU-KG.compute.prompt-management-ahe-rollback)
    # ─────────────────────────────────────────────────────────────────

    async def list_prompts(self) -> list[dict[str, Any]]:
        """List all prompts from the KG.

        CONCEPT:TU-KG.compute.prompt-management-ahe-rollback — Prompt Management
        """
        response = await self._http_client.get(f"{self.base_url}/api/enhanced/prompts")
        response.raise_for_status()
        return response.json()

    async def get_prompt(self, prompt_id: str) -> dict[str, Any]:
        """Get a single prompt by ID.

        CONCEPT:TU-KG.compute.prompt-management-ahe-rollback — Prompt Management
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

        CONCEPT:TU-KG.compute.prompt-management-ahe-rollback — Prompt Management
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/prompts",
            json={"name": name, "content": content, "description": description},
        )
        response.raise_for_status()
        return response.json()

    async def update_prompt(self, prompt_id: str, content: str) -> dict[str, Any]:
        """Update a prompt (creates new version via SUPERSEDES).

        CONCEPT:TU-KG.compute.prompt-management-ahe-rollback — Prompt Management
        """
        response = await self._http_client.put(
            f"{self.base_url}/api/enhanced/prompts/{prompt_id}",
            json={"content": content},
        )
        response.raise_for_status()
        return response.json()

    async def get_prompt_versions(self, prompt_id: str) -> list[dict[str, Any]]:
        """Get version history for a prompt.

        CONCEPT:TU-KG.compute.prompt-management-ahe-rollback — Prompt Management
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/prompts/{prompt_id}/versions"
        )
        response.raise_for_status()
        return response.json()

    async def rollback_prompt(self, prompt_id: str, version_id: str) -> dict[str, Any]:
        """Rollback a prompt to a previous version.

        CONCEPT:TU-KG.compute.prompt-management-ahe-rollback
        Prompt Management (AHE Rollback).
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/prompts/{prompt_id}/rollback/{version_id}"
        )
        response.raise_for_status()
        return response.json()

    # ─────────────────────────────────────────────────────────────────
    #  Granular Resource Queries (CONCEPT:TU-KG.compute.granular-resource-queries)
    # ─────────────────────────────────────────────────────────────────

    async def list_skills_only(self) -> list[dict[str, Any]]:
        """List skills only (no MCP tools).

        CONCEPT:TU-KG.compute.granular-resource-queries — Granular Resource Queries
        """
        response = await self._http_client.get(f"{self.base_url}/api/enhanced/skills")
        response.raise_for_status()
        return response.json()

    async def list_tools_only(self) -> list[dict[str, Any]]:
        """List MCP tools only (no skills).

        CONCEPT:TU-KG.compute.granular-resource-queries — Granular Resource Queries
        """
        response = await self._http_client.get(f"{self.base_url}/api/enhanced/tools")
        response.raise_for_status()
        return response.json()

    async def toggle_resource(self, resource_id: str) -> dict[str, Any]:
        """Toggle enabled/disabled on any skill or tool.

        CONCEPT:TU-KG.compute.granular-resource-queries — Granular Resource Queries
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
