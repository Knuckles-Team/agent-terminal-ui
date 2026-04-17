import pytest
from unittest.mock import AsyncMock, patch
from agent_terminal_ui.client import AgentClient

@pytest.fixture
def run_client():
    client = AgentClient()
    return client

@pytest.mark.asyncio
async def test_create_session(run_client):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.raise_for_status = lambda: None
        mock_response.json.return_value = {"session_id": "test_123"}
        mock_post.return_value = mock_response

        session_id = await run_client.create_session()
        assert session_id == "test_123"

@pytest.mark.asyncio
async def test_stream_mode_injection(run_client):
    with patch.object(run_client, "create_session", return_value="sess_1"), \
         patch.object(run_client, "send_rpc", new_callable=AsyncMock) as mock_rpc, \
         patch.object(run_client, "stream_events") as mock_stream:

        # Make stream return empty
        async def empty_gen(*args, **kwargs):
            for _ in []:
                yield
        mock_stream.side_effect = empty_gen

        async for _ in run_client.stream("/plan list files"):
            pass

        mock_rpc.assert_called_with(
            "sess_1", "message/send", {"content": "list files", "modeId": "plan", "parts": []}
        )
