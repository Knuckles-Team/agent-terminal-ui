#!/usr/bin/python
# coding: utf-8
"""Agent Client implementation for the terminal UI.

This module provides high-level client wrappers for interacting with the agent
server using the native Agent Communication Protocol (ACP).
"""

from collections.abc import AsyncGenerator
import logging
from typing import Any, Optional

from agent_client_protocol import ACPClient

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
        self.client = ACPClient(base_url=self.acp_url)

    async def stream(
        self,
        query: str,
        session_id: Optional[str] = None,
        parts: Optional[list[dict[str, Any]]] = None,
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
                session_id = await self.client.create_session()

            # Send the prompt as an RPC call
            await self.client.send_rpc(
                session_id, "prompt", {"query": query, "parts": parts or []}
            )

            # Stream events from the session
            async for event in self.client.stream_events(session_id):
                # Standardize events for the TUI to consume
                event_type = event.get("type")
                if event_type == "text-delta":
                    yield {"type": "text", "content": event.get("text", "")}
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
                elif event_type == "tool-call":
                    yield {"type": "tool_call", "data": event.get("call")}
                elif event_type == "error":
                    yield {
                        "type": "error",
                        "message": event.get("message", "Unknown error"),
                    }
                else:
                    yield event

        except Exception as e:
            logger.exception(f"ACP Stream Error: {e}")
            yield {"type": "error", "message": str(e)}

    async def send_decision(
        self,
        session_id: str,
        call_id: str,
        decision: str,
        feedback: Optional[str] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Send tool approval decisions back to the agent.

        Args:
            session_id: The active session ID.
            call_id: The ID of the tool call being decided.
            decision: 'accept' or 'reject'.
            feedback: Optional feedback for the agent.
        """
        try:
            await self.client.send_rpc(
                session_id,
                "approve_tool",
                {"call_id": call_id, "decision": decision, "feedback": feedback},
            )
            # Re-yield events if necessary (the stream_events generator above usually handles continuation)
        except Exception as e:
            logger.error(f"Decision Error: {e}")
            yield {"type": "error", "message": str(e)}

    async def get_metadata(self) -> dict[str, Any]:
        """Fetch general agent metadata."""
        try:
            async with self.client._http_client as hc:
                response = await hc.get(f"{self.base_url}/a2a")
                return response.json()
        except Exception:
            return {}

    async def close(self) -> None:
        """Close the client."""
        await self.client.close()
