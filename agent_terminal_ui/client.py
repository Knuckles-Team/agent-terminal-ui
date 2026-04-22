#!/usr/bin/python
"""Agent Client implementation for the terminal UI.

This module provides high-level client wrappers for interacting with the agent
server using the native Agent Communication Protocol (ACP).
"""

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
        self, session_id: str, method: str, params: dict[str, Any]
    ) -> None:
        """Send a JSON-RPC request to the ACP session."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": {"sessionId": session_id, **params},
            "id": 1,
        }
        response = await self._http_client.post(
            f"{self.acp_url}/rpc/{session_id}", json=payload
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

            # Send the prompt as an RPC call
            rpc_params = {"content": query, "modeId": mode_id, "parts": parts or []}
            if model:
                rpc_params["model"] = model
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
                            try:
                                import yaml

                                yaml_data = yaml.safe_load("\n".join(yaml_content))
                                if (
                                    isinstance(yaml_data, dict)
                                    and "description" in yaml_data
                                ):
                                    description = yaml_data["description"]
                            except ImportError:
                                # YAML not available, fall back to simple parsing
                                pass
                            except Exception:
                                # YAML parsing failed, fall back to simple parsing
                                pass

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

    async def close(self) -> None:
        """Close the client."""
        await self._http_client.aclose()


# Alias for backward compatibility and protocol-specific naming
ACPClient = AgentClient
