"""Compose and submit through the real native terminal and public A2A wire."""

import json
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from tests.test_native_public_details_pty import NativeTerminal

pytestmark = [
    pytest.mark.spec("TUIG-RUNTIME-R012.1.3"),
    pytest.mark.skipif(
        not os.environ.get("TUI_NATIVE_TEST_BINARY"),
        reason="Set TUI_NATIVE_TEST_BINARY to the current compiled executable",
    ),
]


@contextmanager
def composer_terminal(
    outcome: str = "completed", *, observe: bool = False
) -> Iterator[NativeTerminal]:
    requests: list[tuple[str, dict[str, Any] | None, str | None]] = []
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def respond(self, value: dict[str, Any], status: int = 200) -> None:
            payload = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self) -> None:
            requests.append((self.path, None, self.headers.get("Authorization")))
            self.respond({"name": "Composer fixture"})

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body, self.headers.get("Authorization")))
            method = body.get("method")
            if method == "message/send" and outcome == "held":
                release.wait(timeout=15)
            if outcome == "unknown":
                self.respond({"error": "unavailable"}, 503)
                return
            state = (
                "canceled"
                if method == "tasks/cancel"
                else "submitted"
                if method == "message/send"
                else outcome
            )
            task: dict[str, Any] = {
                "kind": "task",
                "id": "composer-task",
                "contextId": "composer-context",
                "metadata": {"arbora": {"runId": "composer-run"}},
                "status": {"state": state},
            }
            if state == "completed":
                task["artifacts"] = [
                    {"parts": [{"kind": "text", "text": "Composed native answer"}]}
                ]
            self.respond({"jsonrpc": "2.0", "id": body["id"], "result": task})

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    terminal = NativeTerminal(
        server,
        requests,
        task_id=None,
        arguments=("--observe-task", "composer-task") if observe else (),
    )
    try:
        terminal.wait_until(
            lambda: (
                ("read-only observation" if observe else "Compose one task")
                in terminal.shown()
            )
        )
        yield terminal
    finally:
        release.set()
        terminal.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def mutations(terminal: NativeTerminal) -> list[dict[str, Any]]:
    return [body for _, body, _ in terminal.requests if body is not None]


def test_native_composer_preserves_draft_and_submits_exact_unicode_paste() -> None:
    with composer_terminal() as terminal:
        terminal.send(b"\r")
        terminal.wait_until(lambda: "Prompt must contain text" in terminal.shown())
        assert mutations(terminal) == []
        terminal.send("qcli café".encode())
        terminal.wait_until(lambda: "qcli café" in terminal.shown())
        terminal.send(b"\x1b")
        terminal.wait_until(lambda: "Compose one task" not in terminal.shown())
        terminal.send(b"p")
        terminal.wait_until(lambda: "Compose one task" in terminal.shown())
        assert "qcli café" in terminal.shown()
        terminal.send(b"\x1b[200~\r\nsecond line\x1b[201~")
        terminal.wait_until(lambda: "second line" in terminal.shown())
        terminal.send(b"\x1b[17~")
        terminal.send(b"\r\r\r")
        terminal.wait_until(lambda: "Composed native answer" in terminal.shown())
        assert "composer-task" in terminal.shown()
        assert "composer-context" in terminal.shown()
        assert "composer-run" in terminal.shown()
        sent = [
            body for body in mutations(terminal) if body["method"] == "message/send"
        ]
        assert len(sent) == 1
        assert sent[0]["params"]["message"]["parts"] == [
            {"kind": "text", "text": "qcli café\nsecond line"}
        ]
        assert sent[0]["params"]["configuration"] == {"blocking": False}
        assert all(auth is None for _, _, auth in terminal.requests)
        terminal.send(b"p\r")
        terminal.send(b"\x1b[17~")
        terminal.quit()
        assert (
            len([b for b in mutations(terminal) if b["method"] == "message/send"]) == 1
        )


@pytest.mark.parametrize("outcome", ["unknown", "held"])
def test_native_composer_unknown_or_local_cancel_never_replays(outcome: str) -> None:
    with composer_terminal(outcome) as terminal:
        terminal.send(b"one mutation\r")
        terminal.wait_until(lambda: len(mutations(terminal)) == 1)
        if outcome == "held":
            terminal.send(b"c")
        terminal.wait_until(lambda: "Submission outcome unknown" in terminal.shown())
        terminal.send(b"pr\r")
        terminal.quit()
        assert [body["method"] for body in mutations(terminal)] == ["message/send"]


def test_native_composer_remote_cancel_requires_confirmation() -> None:
    with composer_terminal("working") as terminal:
        terminal.send(b"task to cancel\r")
        terminal.wait_until(lambda: "State: working" in terminal.shown())
        terminal.send(b"x")
        terminal.wait_until(lambda: "Cancel selected remote task?" in terminal.shown())
        terminal.send(b"n")
        terminal.wait_until(
            lambda: "Cancel selected remote task?" not in terminal.shown()
        )
        assert not any(body["method"] == "tasks/cancel" for body in mutations(terminal))
        terminal.send(b"x")
        terminal.wait_until(lambda: "Cancel selected remote task?" in terminal.shown())
        terminal.send(b"y")
        terminal.wait_until(lambda: "State: canceled" in terminal.shown())
        terminal.quit()
        canceled = [
            body for body in mutations(terminal) if body["method"] == "tasks/cancel"
        ]
        assert len(canceled) == 1
        assert canceled[0]["params"]["id"] == "composer-task"


def test_native_composer_resize_and_quit_preserve_terminal_without_submission() -> None:
    termios = pytest.importorskip("termios")
    with composer_terminal() as terminal:
        terminal.send("Draft λ".encode())
        terminal.wait_until(lambda: "Draft λ" in terminal.shown())
        terminal.resize(12, 40)
        terminal.wait_until(lambda: "Draft λ" in terminal.shown())
        terminal.resize(40, 100)
        terminal.wait_until(lambda: "Draft λ" in terminal.shown())
        terminal.send(b"\x03")
        assert terminal.process.wait(timeout=5) == 0
        assert termios.tcgetattr(terminal.master) == terminal.original_terminal
        assert mutations(terminal) == []


@pytest.mark.parametrize("paste", [b"\x1b[31mq\r", b"\x03x\r"])
def test_native_composer_rejects_control_paste_without_dispatch(paste: bytes) -> None:
    with composer_terminal() as terminal:
        terminal.send(b"\x1b[200~" + paste + b"\x1b[201~")
        terminal.wait_until(lambda: "Input rejected" in terminal.shown())
        assert "Compose one task" in terminal.shown()
        assert mutations(terminal) == []
        terminal.send(b"\r")
        terminal.wait_until(lambda: "Prompt must contain text" in terminal.shown())
        assert mutations(terminal) == []
        terminal.send(b"\x03")
        assert terminal.process.wait(timeout=5) == 0


def test_native_observer_cannot_compose_or_cancel() -> None:
    with composer_terminal("working", observe=True) as terminal:
        terminal.wait_until(lambda: "State: working" in terminal.shown())
        terminal.send(b"p\rxy")
        terminal.send(b"r")
        terminal.wait_until(lambda: len(mutations(terminal)) >= 2)
        terminal.quit()
        assert all(body["method"] == "tasks/get" for body in mutations(terminal))
        assert "Compose one task" not in terminal.shown()
        assert "Cancel selected remote task?" not in terminal.shown()
