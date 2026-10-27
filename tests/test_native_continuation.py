"""Exercise the real native continuation entry point against a wire fixture."""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TUI_NATIVE_TEST_BINARY"),
    reason="Requires an explicitly built native executable",
)

EXTENSION = "https://knuckles-team.github.io/arbora/extensions/completed-text-history/v1"
CONTEXT = "a2a-context-" + "a" * 64


@pytest.mark.spec("TUI-RUNTIME-R012.3.2.1")
@pytest.mark.parametrize("outcome", ["accepted", "legacy", "missing-echo", "changed-context"])
def test_native_continue_requires_capability_activation_and_bound_context(outcome):
    requests: list[tuple[str, dict[str, Any] | None, str | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, payload, activation=False):
            encoded = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(encoded)))
            if activation:
                self.send_header("X-A2A-Extensions", EXTENSION)
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            requests.append((self.path, None, None))
            assert self.path == "/.well-known/agent-card.json"
            capabilities: dict[str, object] = {"stateTransitionHistory": True}
            if outcome != "legacy":
                capabilities["extensions"] = [{"uri": EXTENSION, "required": False}]
            self.reply({"capabilities": capabilities})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body, self.headers.get("Idempotency-Key")))
            assert self.headers.get("X-A2A-Extensions") == EXTENSION
            assert self.path == "/a2a"
            self.reply(
                {"jsonrpc": "2.0", "id": body["id"], "result": {
                    "kind": "task", "id": "task-fixture",
                    "contextId": "changed-context" if outcome == "changed-context" else CONTEXT,
                    "status": {"state": "completed"},
                    "artifacts": [{"parts": [{"kind": "text", "text": "bound reply"}]}],
                }},
                activation=outcome != "missing-echo",
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    environment = {key: value for key, value in os.environ.items() if not key.startswith("AGENT_")}
    environment.update(AGENT_URL=f"http://127.0.0.1:{server.server_port}", AGENT_AUTH_MODE="none")
    try:
        for _ in range(2 if outcome == "accepted" else 1):
            result = subprocess.run(
                [str(Path(os.environ["TUI_NATIVE_TEST_BINARY"]).resolve()), "--headless",
                 "--continue", CONTEXT, "--prompt", "latest prompt only"],
                env=environment, stdin=subprocess.DEVNULL, capture_output=True,
                text=True, timeout=15, check=False,
            )
            assert (result.returncode == 0) is (outcome == "accepted"), result.stderr
            if outcome == "accepted":
                assert "bound reply" in result.stdout
            elif outcome == "legacy":
                assert "no turn was submitted" in result.stderr
            else:
                assert "Submission outcome unknown" in result.stderr
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    posts = [(body, key) for path, body, key in requests if path == "/a2a" and body is not None]
    assert len(posts) == (0 if outcome == "legacy" else 2 if outcome == "accepted" else 1)
    assert len(requests) == (1 if outcome == "legacy" else 4 if outcome == "accepted" else 2)
    for body, key in posts:
        assert body["method"] == "message/send"
        assert body["id"] == key == body["params"]["message"]["messageId"]
        assert body["params"]["message"]["contextId"] == CONTEXT
        assert body["params"]["message"]["parts"] == [{"kind": "text", "text": "latest prompt only"}]
    if outcome == "accepted":
        assert posts[0][1] != posts[1][1]
