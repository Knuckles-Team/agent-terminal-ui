#!/usr/bin/python
# coding: utf-8
"""Agent Client implementation for the terminal UI.

This module provides high-level client wrappers for interacting with the agent
server using the native Agent Communication Protocol (ACP).
"""

from collections.abc import AsyncGenerator
import json
import logging
import httpx
from typing import Any, Optional, Dict

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
        self, session_id: str, method: str, params: Dict[str, Any]
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
    ) -> AsyncGenerator[Dict[str, Any], None]:
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
        session_id: Optional[str] = None,
        parts: Optional[list[dict[str, Any]]] = None,
        mode_id: Optional[str] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream real-time events from the ACP session.

        Args:
            query: The user prompt to send to the agent.
            session_id: Optional existing session ID to resume.
            parts: Optional list of multi-modal message parts.

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
            await self.send_rpc(
                session_id,
                "message/send",
                {"content": query, "modeId": mode_id, "parts": parts or []},
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
        feedback: Optional[str] = None,
        session_id: Optional[str] = None,
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

    async def close(self) -> None:
        """Close the client."""
        await self._http_client.aclose()


# Alias for backward compatibility and protocol-specific naming
ACPClient = AgentClient
