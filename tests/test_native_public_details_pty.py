"""Optional compiled-native acceptance through a real terminal and local HTTP."""

import codecs
import json
import os
import select
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

pty = pytest.importorskip("pty")
termios = pytest.importorskip("termios")
pyte = pytest.importorskip("pyte")
OWNER_TASK_ID = "work-item:" + "a" * 64

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("TUI_NATIVE_TEST_BINARY"),
        reason="Set TUI_NATIVE_TEST_BINARY to an explicitly built native executable",
    ),
]


class NativeTerminal:
    """Drive the real executable through a PTY and inspect its rendered cells."""

    def __init__(
        self,
        server: ThreadingHTTPServer,
        requests: list[tuple[str, dict[str, Any] | None, str | None]],
        task_id: str = OWNER_TASK_ID,
        *,
        no_color: bool = True,
    ) -> None:
        self.requests = requests
        self.trace: deque[tuple[str, object]] = deque(maxlen=64)
        self.master, slave = pty.openpty()
        termios.tcsetwinsize(slave, (40, 100))
        self.original_terminal = termios.tcgetattr(slave)
        environment = {
            **os.environ,
            "TERM": "xterm-256color",
            "NO_COLOR": "1" if no_color else "",
            "AGENT_URL": f"http://127.0.0.1:{server.server_port}",
            "AGENT_TASK_ID": task_id,
            "AGENT_AUTH_MODE": "none",
            "HTTP_PROXY": "http://127.0.0.1:1",
            "HTTPS_PROXY": "http://127.0.0.1:1",
        }
        environment.pop("AGENT_BEARER_TOKEN", None)
        try:
            self.process = subprocess.Popen(
                [os.environ["TUI_NATIVE_TEST_BINARY"]],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                env=environment,
            )
        finally:
            os.close(slave)
        self.screen = pyte.Screen(100, 40)
        self.stream = pyte.Stream(self.screen)
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")

    def shown(self) -> str:
        return "\n".join(self.screen.display)

    def send(self, keys: bytes) -> None:
        self.trace.append(("send", keys))
        os.write(self.master, keys)

    def wait_until(self, predicate: Callable[[], bool]) -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if predicate():
                return
            if self.process.poll() is not None:
                pytest.fail(f"Native process exited early: {self.process.returncode}")
            if select.select([self.master], [], [], 0.05)[0]:
                raw = os.read(self.master, 65536)
                self.trace.append(("read", raw[-4096:]))
                if b"\x1b[6n" in raw:
                    self.send(b"\x1b[1;1R")
                self.stream.feed(self.decoder.decode(raw))
        pytest.fail(
            f"Terminal expectation timed out:\n{self.shown()}"
            f"\nRequests: {self.requests}"
            f"\nPTY events: {list(self.trace)}"
        )

    def resize(self, rows: int, columns: int, *, wait_for_frame: bool = True) -> None:
        self.trace.append(("resize", (rows, columns)))
        self.screen.resize(lines=rows, columns=columns)
        termios.tcsetwinsize(self.master, (rows, columns))
        os.kill(self.process.pid, signal.SIGWINCH)
        if not wait_for_frame:
            return
        # pyte clips the old frame on resize; its copied footer is not a redraw.
        self.wait_until(
            lambda: (
                self.screen.display[0].startswith("┌")
                and self.screen.display[0].endswith("┐")
                and self.screen.display[-1].startswith("└")
                and self.screen.display[-1].endswith("┘")
            )
        )

    def quit(self) -> None:
        self.send(b"q")
        assert self.process.wait(timeout=5) == 0
        assert termios.tcgetattr(self.master) == self.original_terminal

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)
        os.close(self.master)


@pytest.mark.spec("TUI-RUNTIME-R008.2.3.2.2.1")
def test_native_inline_folds_keyboard_mouse_refresh_and_quit_do_not_write_tasks():
    value = json.loads(
        (Path(__file__).parents[0] / "fixtures/public_run_events.json").read_text()
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
    terminal = NativeTerminal(server, requests)
    shown = terminal.shown
    wait_until = terminal.wait_until

    def event_reads():
        return [body for path, body, _ in requests if path == "/api/v1/ops/runs.events"]

    try:
        wait_until(lambda: "Visible answer" in shown() and "Execution trace" in shown())
        assert not event_reads()
        assert "Public explanation:" not in shown() and "task_started" not in shown()
        terminal.send(b"\t\r")
        wait_until(lambda: "Public explanation:" in shown())
        assert "[bold]literal[/bold]" in shown() and "task_started" not in shown()
        terminal.send(b" \t\r")
        wait_until(
            lambda: "task_started" in shown() and "Public explanation:" not in shown()
        )
        row = next(
            i
            for i, line in enumerate(terminal.screen.display, 1)
            if "Public model summary" in line
        )
        terminal.send(f"\x1b[<0;3;{row}M\x1b[<0;3;{row}m".encode())
        wait_until(
            lambda: "Public explanation:" in shown() and "task_started" in shown()
        )
        terminal.send(b" r")
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
                "task_id": OWNER_TASK_ID,
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
        terminal.quit()
    finally:
        terminal.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.spec("TUI-RUNTIME-R010", "TUI-RUNTIME-R010.11", "TUI-RUNTIME-R010.12")
def test_native_graph_real_binding_navigation_resize_refresh_denial_and_quit():
    value = json.loads(
        (
            Path(__file__).parents[0] / "fixtures/execution_graph_contract.json"
        ).read_text()
    )["value"]
    requests: list[tuple[str, dict[str, Any] | None, str | None]] = []
    refresh_arrived = threading.Event()
    release_refresh = threading.Event()

    def graph_reads() -> list[dict[str, Any] | None]:
        return [
            body
            for path, body, _ in requests
            if path == "/api/v1/ops/runs.execution_graph"
        ]

    class Handler(BaseHTTPRequestHandler):
        def respond(self, body: dict[str, Any], status: int = 200) -> None:
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            requests.append((self.path, None, self.headers.get("Authorization")))
            if self.path != "/api/v1/registry":
                self.respond({"error": "unexpected route"}, 404)
                return
            self.respond(
                {
                    "api_version": "v1",
                    "registry_digest": "graph-pty-fixture",
                    "ops": [{"id": "runs.execution_graph"}],
                }
            )

        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            if not 0 < length <= 65536:
                self.respond({"error": "request bound"}, 413)
                return
            body = json.loads(self.rfile.read(length))
            requests.append((self.path, body, self.headers.get("Authorization")))
            if self.path == "/a2a" and body.get("method") == "tasks/get":
                self.respond(
                    {
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "result": {
                            "kind": "task",
                            "id": value["task_id"],
                            "contextId": "graph-pty-context",
                            "status": {"state": "completed"},
                            "metadata": {"arbora": {"runId": value["run_id"]}},
                            "artifacts": [
                                {
                                    "parts": [
                                        {"kind": "text", "text": "Bound graph task"}
                                    ]
                                }
                            ],
                        },
                    }
                )
                return
            if self.path != "/api/v1/ops/runs.execution_graph":
                self.respond({"error": "unexpected route"}, 404)
                return
            if len(graph_reads()) == 2:
                refresh_arrived.set()
                if not release_refresh.wait(timeout=10):
                    self.respond({"error": "refresh was not released"}, 503)
                    return
            if len(graph_reads()) == 3:
                self.respond({"error": "denied"}, 403)
                return
            self.respond(
                {
                    "ok": True,
                    "meta": {
                        "api_version": "v1",
                        "registry_digest": "graph-pty-fixture",
                    },
                    "result": {"value": value},
                }
            )

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    terminal = NativeTerminal(server, requests, value["task_id"])
    shown = terminal.shown
    wait_until = terminal.wait_until
    try:
        wait_until(
            lambda: "Bound graph task" in shown() and "graph-pty-context" in shown()
        )
        assert not graph_reads()
        terminal.send(b"i")
        wait_until(
            lambda: "Run inspector (read-only)" in shown() and "unavailable" in shown()
        )
        assert not graph_reads()
        terminal.send(b"g")
        wait_until(
            lambda: (
                "> 1. first [running]" in shown()
                and "Message active child: unavailable" in shown()
            )
        )
        assert "Flat execution DAG (read-only)" in shown()
        for row in (
            "1. first [running]",
            "2. left [unobserved]",
            "3. right [unobserved]",
            "4. join [unobserved]",
        ):
            assert shown().count(row) == 1
        assert "Dependents (depends_on): 2: left, 3: right" in shown()
        assert "Public event evidence: event-2 (sequence 2)" in shown()
        assert "Unobserved means unknown, not pending." in shown()
        assert "Spawned children: unsupported" in shown()
        assert "Message active child: unavailable" in shown()

        terminal.send(b"\x1b[Z")
        wait_until(
            lambda: (
                "> 4. join [unobserved]" in shown()
                and "Predecessors (depends_on): 2: left, 3: right" in shown()
                and "Public event evidence: unavailable" in shown()
            )
        )
        assert "Predecessors (depends_on): 2: left, 3: right" in shown()
        assert "Dependents (depends_on): none" in shown()
        assert "Public event evidence: unavailable" in shown()
        terminal.resize(24, 40)
        terminal.send(b"\x1b[F")
        wait_until(lambda: "Escape: close | q: quit" in shown())
        assert "Message active child: unavailable" in shown()
        assert "Continue completed child: unavailable" in shown()
        terminal.send(b"\t")
        wait_until(lambda: "> 1. first [running]" in shown())
        terminal.send(b"\x1b[Z")
        wait_until(lambda: "> 4. join [unobserved]" in shown())
        terminal.resize(40, 100)
        wait_until(lambda: "Predecessors (depends_on): 2: left, 3: right" in shown())
        assert "> 4. join [unobserved]" in shown()
        # Keep the original rapid sequence covered independently of the frame fence.
        terminal.resize(24, 40, wait_for_frame=False)
        terminal.send(b"\x1b[F\t")
        wait_until(
            lambda: (
                "> 1. first [running]" in shown()
                and terminal.screen.display[0].endswith("┐")
            )
        )
        terminal.send(b"\x1b[Z")
        wait_until(lambda: "> 4. join [unobserved]" in shown())
        terminal.resize(40, 100)
        wait_until(lambda: "Predecessors (depends_on): 2: left, 3: right" in shown())
        assert "> 4. join [unobserved]" in shown()
        assert len(graph_reads()) == 1

        terminal.send(b"r")
        wait_until(
            lambda: refresh_arrived.is_set() and "Reading execution graph..." in shown()
        )
        assert "first [running]" not in shown() and "join [unobserved]" not in shown()
        assert "Public event evidence:" not in shown()
        release_refresh.set()
        wait_until(lambda: "> 1. first [running]" in shown())
        assert "> 4. join" not in shown()
        terminal.send(b"\x1b[Z")
        wait_until(lambda: "> 4. join [unobserved]" in shown())
        terminal.send(b"r")
        wait_until(lambda: "Execution graph denied; protected data cleared" in shown())
        assert "first [running]" not in shown() and "join [unobserved]" not in shown()
        assert "Public event evidence:" not in shown()

        terminal.send(b"\x1b")
        wait_until(
            lambda: (
                "Bound graph task" in shown()
                and "Run inspector (read-only)" not in shown()
            )
        )
        terminal.send(b"i")
        wait_until(
            lambda: "Run inspector (read-only)" in shown() and "unavailable" in shown()
        )
        terminal.send(b"g")
        wait_until(lambda: "> 1. first [running]" in shown())
        assert "> 4. join" not in shown()
        assert len(graph_reads()) == 4
        assert all(
            body
            == {
                "schema_version": "arbora-execution-graph-v1",
                "run_id": value["run_id"],
                "task_id": value["task_id"],
            }
            for body in graph_reads()
        )
        task_reads = [body for path, body, _ in requests if path == "/a2a"]
        assert len(task_reads) == 1
        assert isinstance(task_reads[0], dict)
        assert task_reads[0]["method"] == "tasks/get"
        assert task_reads[0]["params"]["id"] == value["task_id"]
        assert all(
            path in {"/a2a", "/api/v1/registry", "/api/v1/ops/runs.execution_graph"}
            and auth is None
            for path, _, auth in requests
        )
        terminal.quit()
    finally:
        release_refresh.set()
        terminal.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
