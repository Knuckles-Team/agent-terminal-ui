"""Optional compiled-native acceptance through a real terminal and local HTTP."""

import codecs
import json
import os
import select
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

pty = pytest.importorskip("pty")
termios = pytest.importorskip("termios")
pyte = pytest.importorskip("pyte")
OWNER_TASK_ID = "work-item:" + "a" * 64

pytestmark = [
    pytest.mark.spec("TUI-RUNTIME-R008.2.3.2.2.1"),
    pytest.mark.skipif(
        not os.environ.get("TUI_NATIVE_TEST_BINARY"),
        reason="Set TUI_NATIVE_TEST_BINARY to an explicitly built native executable",
    ),
]


def test_native_inline_folds_keyboard_mouse_refresh_and_quit_do_not_write_tasks():
    value = json.loads(
        (Path(__file__).parent / "fixtures/public_run_events.json").read_text()
    )
    requests: list[tuple[str, dict[str, Any] | None, str | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def respond(self, body):
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            requests.append((self.path, None, self.headers.get("Authorization")))
            self.respond(
                {
                    "api_version": "v1",
                    "registry_digest": "fixture",
                    "ops": [{"id": "runs.events"}],
                }
            )

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body, self.headers.get("Authorization")))
            if self.path == "/api/v1/ops/runs.events":
                self.respond(
                    {
                        "ok": True,
                        "meta": {"api_version": "v1", "registry_digest": "fixture"},
                        "result": {"value": value},
                    }
                )
            else:
                self.respond(
                    {
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "result": {
                            "kind": "task",
                            "id": OWNER_TASK_ID,
                            "contextId": "context-1",
                            "status": {"state": "completed"},
                            "metadata": {"arbora": {"runId": "run-1"}},
                            "artifacts": [
                                {"parts": [{"kind": "text", "text": "Visible answer"}]}
                            ],
                        },
                    }
                )

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    master, slave = pty.openpty()
    termios.tcsetwinsize(slave, (40, 100))
    environment = {
        **os.environ,
        "TERM": "xterm-256color",
        "NO_COLOR": "1",
        "AGENT_URL": f"http://127.0.0.1:{server.server_port}",
        "AGENT_TASK_ID": OWNER_TASK_ID,
        "AGENT_AUTH_MODE": "none",
        "HTTP_PROXY": "http://127.0.0.1:1",
        "HTTPS_PROXY": "http://127.0.0.1:1",
    }
    environment.pop("AGENT_BEARER_TOKEN", None)
    process = subprocess.Popen(
        [os.environ["TUI_NATIVE_TEST_BINARY"]],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=environment,
    )
    os.close(slave)
    screen = pyte.Screen(100, 40)
    stream = pyte.Stream(screen)
    decoder = codecs.getincrementaldecoder("utf-8")("replace")

    def shown():
        return "\n".join(screen.display)

    def wait_until(predicate):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if predicate():
                return
            if select.select([master], [], [], 0.05)[0]:
                raw = os.read(master, 65536)
                if b"\x1b[6n" in raw:
                    os.write(master, b"\x1b[1;1R")
                stream.feed(decoder.decode(raw))
        pytest.fail(f"Terminal expectation timed out:\n{shown()}\nRequests: {requests}")

    def event_reads():
        return [body for path, body, _ in requests if path == "/api/v1/ops/runs.events"]

    try:
        wait_until(lambda: "Visible answer" in shown() and "Execution trace" in shown())
        assert not event_reads()
        assert "Public explanation:" not in shown() and "task_started" not in shown()
        os.write(master, b"\t\r")
        wait_until(lambda: "Public explanation:" in shown())
        assert "[bold]literal[/bold]" in shown() and "task_started" not in shown()
        os.write(master, b" \t\r")
        wait_until(
            lambda: "task_started" in shown() and "Public explanation:" not in shown()
        )
        row = next(
            i
            for i, line in enumerate(screen.display, 1)
            if "Public model summary" in line
        )
        os.write(master, f"\x1b[<0;3;{row}M\x1b[<0;3;{row}m".encode())
        wait_until(
            lambda: "Public explanation:" in shown() and "task_started" in shown()
        )
        os.write(master, b" r")
        wait_until(
            lambda: (
                len(event_reads()) == 2
                and "task_started" in shown()
                and "Public explanation:" not in shown()
            )
        )
        assert all(
            body
            == {
                "run_id": "run-1",
                "task_id": environment["AGENT_TASK_ID"],
                "after": 0,
                "limit": 1000,
            }
            for body in event_reads()
        )
        rpc = [
            body
            for path, body, _ in requests
            if path != "/api/v1/ops/runs.events" and body
        ]
        assert len(rpc) == 2 and all(body["method"] == "tasks/get" for body in rpc)
        assert all(auth is None for _, _, auth in requests)
        os.write(master, b"q")
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        os.close(master)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
