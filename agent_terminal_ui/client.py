from collections.abc import AsyncGenerator
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AgentClient:
    """Client for the agent-utilities AG-UI streaming protocol."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=None)

    async def stream(
        self, query: str, session_id: str | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream events from the /ag-ui endpoint."""
        url = f"{self.base_url}/ag-ui"
        payload = {"query": query}
        if session_id:
            payload["session_id"] = session_id

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
                            # Try to parse if it's a JSON string (e.g. "Drafting...")
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
        """Fetch general agent metadata."""
        try:
            response = await self._client.get(f"{self.base_url}/a2a")
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching metadata: {e}")
            return {}

    async def list_chats(self) -> list[dict[str, Any]]:
        """Fetch list of chat sessions."""
        try:
            response = await self._client.get(f"{self.base_url}/chats")
            return response.json()
        except Exception as e:
            logger.error(f"Error listing chats: {e}")
            return []

    async def get_chat(self, chat_id: str) -> dict[str, Any]:
        """Fetch full chat details."""
        try:
            response = await self._client.get(f"{self.base_url}/chats/{chat_id}")
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching chat {chat_id}: {e}")
            return {}

    async def get_mcp_config(self) -> dict[str, Any]:
        """Fetch current MCP configuration."""
        try:
            response = await self._client.get(f"{self.base_url}/mcp/config")
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching MCP config: {e}")
            return {"mcpServers": {}}

    async def list_mcp_tools(self) -> list[dict[str, Any]]:
        """Fetch list of all available MCP tools."""
        try:
            response = await self._client.get(f"{self.base_url}/mcp/tools")
            return response.json()
        except Exception as e:
            logger.error(f"Error listing MCP tools: {e}")
            return []

    async def send_decision(
        self, decisions: dict[str, str], feedback: str | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Send tool approval decisions back to the agent."""
        url = f"{self.base_url}/ag-ui"
        # The protocol for decisions usually involves sending a list of permission events
        # In our case, we'll send them one by one or as a batch if supported.
        # For now, following the pattern in _run_agent_turn_with_permissions

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

    async def close(self):
        await self._client.aclose()


class ACPHttpClient:
    """Client for the pydantic-acp ACP protocol over HTTP/SSE."""

    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=None)

    async def create_session(self) -> str:
        """Create a new ACP session and return its ID."""
        url = f"{self.base_url}/acp/sessions"
        response = await self._client.post(url)
        data = response.json()
        return data["session_id"]

    async def stream(self, session_id: str) -> AsyncGenerator[dict[str, Any], None]:
        """Stream ACP events from the SSE endpoint."""
        url = f"{self.base_url}/acp/stream/{session_id}"
        async with self._client.stream("GET", url) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    content = line[6:]
                    try:
                        yield json.loads(content)
                    except json.JSONDecodeError:
                        continue

    async def send_rpc(self, session_id: str, method: str, params: dict) -> dict:
        """Send a JSON-RPC request to the ACP agent."""
        url = f"{self.base_url}/acp/rpc/{session_id}"
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }
        response = await self._client.post(url, json=payload)
        return response.json()

    async def close(self):
        await self._client.aclose()
