"""Execute native headless commands through pipes, never a Python frontend."""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TUI_NATIVE_TEST_BINARY"),
    reason="Requires an explicitly built native executable",
)


@pytest.mark.spec("TUIG-RUNTIME-R012.1.3.1")
@pytest.mark.parametrize(
    ("outcome", "success", "methods"),
    [
        ("completed", True, ["message/send", "tasks/get"]),
        ("input-required", False, ["message/send", "tasks/get"]),
        ("auth-required", False, ["message/send", "tasks/get"]),
        ("wrong-context", False, ["message/send", "tasks/get"]),
        ("unknown", False, ["message/send"]),
    ],
)
def test_native_headless_submission_observes_without_replay(outcome, success, methods):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            assert self.path == "/a2a"
            assert self.headers.get("Authorization") is None
            if outcome == "unknown":
                self.send_response(503)
                self.end_headers()
                return
            submitting = body["method"] == "message/send"
            task: dict[str, object] = {
                "kind": "task",
                "id": "task-headless",
                "contextId": "wrong-context" if outcome == "wrong-context" and not submitting else "context-headless",
                "metadata": {"arbora": {"runId": "run-headless"}},
                "status": {"state": "submitted" if submitting else ("completed" if outcome == "wrong-context" else outcome)},
            }
            if not submitting and outcome == "completed":
                task["artifacts"] = [{"parts": [{"kind": "text", "text": "native pipe reply"}]}]
            payload = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": task}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    environment = {key: value for key, value in os.environ.items() if not key.startswith("AGENT_")}
    environment.update(AGENT_URL=f"http://127.0.0.1:{server.server_port}", AGENT_AUTH_MODE="none")
    try:
        result = subprocess.run(
            [str(Path(os.environ["TUI_NATIVE_TEST_BINARY"]).resolve()), "--headless", "--prompt", "native fixture"],
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert (result.returncode == 0) is success, result.stderr
    assert [request["method"] for request in requests] == methods
    assert requests[0]["params"]["configuration"]["blocking"] is False
    assert "\x1b[" not in result.stdout
    if success:
        assert "native pipe reply" in result.stdout
    if outcome == "unknown":
        assert "Submission outcome unknown" in result.stderr
    if outcome == "input-required":
        assert "no approval was sent" in result.stderr
