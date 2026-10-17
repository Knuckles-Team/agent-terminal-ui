"""Real loopback reader and mounted metadata/gap display."""
# spec: TUI-RUNTIME-R002.11

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import AsyncMock

import httpx
import pytest
from textual.widgets import RichLog

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.host_logs import AuthenticatedHostLogReader, _batch
from tests.test_host_log_subscription import receipt_payload


@contextmanager
def host():
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, body))
            assert self.headers["Authorization"] == "Bearer local-test"
            if self.path.endswith("reference"):
                status, value = 200, receipt_payload()
            elif len(calls) == 2:
                assert body["version"] == 2 and body["cursor"] is None
                status, value = 200, {
                    "version": 2, "records": [{"host_instance": "original-host", "sequence": 7,
                    "request": "request-original", "timestamp": 123.5, "severity": "WARN",
                    "message": "[red]protected\u001b"}], "cursor": "opaque", "gap": True,
                }
            else:
                assert body["cursor"] == "opaque"
                status, value = 409, {"detail": "retention_gap"}
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.asyncio
async def test_loopback_metadata_then_gap_clears_and_stops(fake_client: AsyncMock):
    with host() as (url, calls):
        async with httpx.AsyncClient(base_url=url, headers={"Authorization": "Bearer local-test"}) as client:
            reader = AuthenticatedHostLogReader(client)
            receipt = await reader.bind()
            app = AgentApp(client=fake_client, host_receipt=receipt, log_reader=reader)
            async with app.run_test(size=(150, 40)) as pilot:
                await app._cmd_processor.cmd_logs("")
                await pilot.pause(0.1)
                log = app.screen.query_one("#server-log", RichLog)
                text = "".join(line.text for line in log.lines)
                assert "host=original-host seq=7 request=request-original" in text
                assert "123.5 WARN" in text and "[red]protected" in text
                assert "history gap" in text and "\u001b" not in text
                await pilot.pause(0.5)
                text = "".join(line.text for line in log.lines)
                assert "resume position is no longer retained" in text
                assert "protected" not in text and "original-host" not in text
                await pilot.pause(0.3)
                assert len(calls) == 3
                assert not reader.accepts(receipt)


@pytest.mark.parametrize("change", [{"sequence": True}, {"sequence": 0}, {"timestamp": float("nan")}, {"timestamp": -1}, {"request": "x" * 1025}, {"severity": ""}])
def test_malformed_metadata_refuses(change):
    row = {"host_instance": "original-host", "sequence": 1, "request": "r", "timestamp": 1.0, "severity": "INFO", "message": "safe"} | change
    with pytest.raises(ValueError):
        _batch({"version": 2, "records": [row], "cursor": None, "gap": False}, 128)
