#!/usr/bin/python
# coding: utf-8
"""Agent Client implementation for the terminal UI.

This module provides high-level client wrappers for interacting with the agent
server. It supports the legacy AG-UI streaming protocol and the modern,
standardized Agent Communication Protocol (ACP) via HTTP/SSE.
"""

from collections.abc import AsyncGenerator
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AgentClient:
    """Client for the agent-utilities AG-UI streaming protocol.

    Provides methods to stream agent events, manage chat sessions,
    retrieve agent metadata, and send tool execution decisions.
    """

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        """Initialize the AG-UI client.

        Args:
            base_url: The base URL of the agent server.

        """
        self.base_url: str = base_url.rstrip("/")
        self._client: httpx.AsyncClient = httpx.AsyncClient(timeout=None)

    async def stream(
        self,
        query: str,
        session_id: str | None = None,
        parts: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream real-time events from the /ag-ui endpoint.

        Args:
            query: The user prompt to send to the agent.
            session_id: Optional existing session ID to resume.
            parts: Optional list of multi-modal message parts.

        Yields:
            Standardized event dictionaries (text, tool_call, sideband, error).

        """
        url = f"{self.base_url}/ag-ui"
        payload: dict[str, Any] = {"query": query}
        if session_id:
            payload["session_id"] = session_id
        if parts:
            payload["parts"] = parts

        async with self._client.stream("POST", url, json=payload) as response:
            if response.status_code != 200:
                error_body = await response.aread()
                yield {
                    "type": "error",
                    "message": f"Server error {response.status_code}: {error_body.decode()}",
                }
                return

            async for line in response.aiter_lines():
                if not line:
                    continue

                # Protocol uses prefixes:
                # 0: Heartbeat
                # 1: Text chunk
                # 2: Tool call / Structured data
                # 8: Sideband / Graph activity
                # 9: Error

                if line.startswith("0:"):
                    continue

                try:
                    prefix, content = line.split(":", 1)
                    if prefix == "1":
                        # Text chunk is usually a JSON string or raw text
                        try:
                            # Try to parse if it's a JSON string
                            chunk = json.loads(content)
                            yield {"type": "text", "content": chunk}
                        except json.JSONDecodeError:
                            yield {"type": "text", "content": content}
                    elif prefix == "2":
                        data = json.loads(content)
                        yield {"type": "tool_call", "data": data}
                    elif prefix == "8":
                        data = json.loads(content)
                        yield {"type": "sideband", "data": data}
                    elif prefix == "9":
                        yield {"type": "error", "message": content}
                    else:
                        # Raw content or unknown prefix
                        yield {"type": "raw", "content": line}
                except Exception as e:
                    logger.error(f"Error parsing stream line: {line} - {e}")
                    yield {"type": "error", "message": f"Parse error: {e}"}

    async def get_metadata(self) -> dict[str, Any]:
        """Fetch general agent metadata from the /a2a endpoint.

        Returns:
            A dictionary containing the agent's identity and capabilities.

        """
        try:
            response = await self._client.get(f"{self.base_url}/a2a")
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching metadata: {e}")
            return {}

    async def list_chats(self) -> list[dict[str, Any]]:
        """Fetch the list of historical chat sessions.

        Returns:
            A list of chat metadata dictionaries.

        """
        try:
            response = await self._client.get(f"{self.base_url}/chats")
            return response.json()
        except Exception as e:
            logger.error(f"Error listing chats: {e}")
            return []

    async def get_chat(self, chat_id: str) -> dict[str, Any]:
        """Fetch the full conversation history for a specific chat.

        Args:
            chat_id: The unique identifier of the chat session.

        Returns:
            The complete chat session object including messages.

        """
        try:
            response = await self._client.get(f"{self.base_url}/chats/{chat_id}")
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching chat {chat_id}: {e}")
            return {}

    async def get_mcp_config(self) -> dict[str, Any]:
        """Fetch the current MCP server configuration.

        Returns:
            The parsed mcp_config.json content from the server.

        """
        try:
            response = await self._client.get(f"{self.base_url}/mcp/config")
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching MCP config: {e}")
            return {"mcpServers": {}}

    async def list_mcp_tools(self) -> list[dict[str, Any]]:
        """Fetch the consolidated list of all available tools across MCP servers.

        Returns:
            A list of tool definition dictionaries.

        """
        try:
            response = await self._client.get(f"{self.base_url}/mcp/tools")
            return response.json()
        except Exception as e:
            logger.error(f"Error listing MCP tools: {e}")
            return []

    async def send_decision(
        self, decisions: dict[str, str], feedback: str | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Send tool approval decisions back to the agent orchestrator.

        Args:
            decisions: Map of tool call IDs to 'accept' or 'reject'.
            feedback: Optional textual feedback from the user.

        Yields:
            Standardized event dictionaries as the agent resumes execution.

        """
        url = f"{self.base_url}/ag-ui"

        for call_id, decision in decisions.items():
            payload = {
                "call_id": call_id,
                "permission": decision,
                "feedback": feedback if feedback else None,
            }
            # Only send feedback with the first decision to avoid duplication
            feedback = None

            async with self._client.stream("POST", url, json=payload) as response:
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        prefix, content = line.split(":", 1)
                        if prefix == "1":
                            yield {"type": "text", "content": json.loads(content)}
                        elif prefix == "2":
                            yield {"type": "tool_call", "data": json.loads(content)}
                        elif prefix == "8":
                            yield {"type": "sideband", "data": json.loads(content)}
                        elif prefix == "9":
                            yield {"type": "error", "message": content}
                    except Exception:
                        continue

    async def close(self) -> None:
        """Close the underlying HTTP client resources."""
        await self._client.aclose()


class ACPHttpClient:
    """Client for the standardized Agent Communication Protocol (ACP) over HTTP/SSE.

    Facilitates structured session management, JSON-RPC communication,
    and SSE-based event streaming.
    """

    def __init__(self, base_url: str = "http://localhost:8001") -> None:
        """Initialize the ACP client.

        Args:
            base_url: The base URL of the ACP-compliant agent server.

        """
        self.base_url: str = base_url.rstrip("/")
        self._client: httpx.AsyncClient = httpx.AsyncClient(timeout=None)

    async def create_session(self) -> str:
        """Create a new ACP session.

        Returns:
            The unique session_id generated by the server.

        """
        url = f"{self.base_url}/acp/sessions"
        response = await self._client.post(url)
        data = response.json()
        return data["session_id"]

    async def stream(self, session_id: str) -> AsyncGenerator[dict[str, Any], None]:
        """Stream real-time events from an active ACP session using SSE.

        Args:
            session_id: The ID of the session to stream from.

        Yields:
            Parsed ACP event dictionaries.

        """
        url = f"{self.base_url}/acp/stream/{session_id}"
        async with self._client.stream("GET", url) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    content = line[6:]
                    try:
                        yield json.loads(content)
                    except json.JSONDecodeError:
                        continue

    async def send_rpc(
        self, session_id: str, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a JSON-RPC request to the ACP agent.

        Args:
            session_id: The ID of the session to send the request to.
            method: The JSON-RPC method name (e.g., 'prompt').
            params: The parameters for the RPC call.

        Returns:
            The JSON response from the RPC call.

        """
        url = f"{self.base_url}/acp/rpc/{session_id}"
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }
        response = await self._client.post(url, json=payload)
        return response.json()

    async def close(self) -> None:
        """Close the underlying HTTP client resources."""
        await self._client.aclose()
