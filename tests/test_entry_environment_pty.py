"""Installed Python and compiled-native environment behavior through real PTYs."""

import codecs
import ctypes
import json
import os
import select
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from tests.test_installed_operator_entry import installed_entry

pty = pytest.importorskip("pty")
termios = pytest.importorskip("termios")
pyte = pytest.importorskip("pyte")
pytestmark = pytest.mark.spec("TUI-RUNTIME-R015.42.2")
BACKGROUNDS = {
    "tokyo-night": "1a1b26", "nord": "2e3440", "gruvbox": "282828",
    "textual-light": "e0e0e0", "unknown-theme": "1a1b26",
}


class LogOpenProbe:
    """Watch actual opens, including an attempted read that produces no output."""

    def __init__(self, path: Path) -> None:
        libc = ctypes.CDLL(None, use_errno=True)
        self.fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        assert self.fd >= 0, os.strerror(ctypes.get_errno())
        watch = libc.inotify_add_watch(self.fd, os.fsencode(path), 0x20)
        assert watch >= 0, os.strerror(ctypes.get_errno())

    def opened(self) -> bool:
        try:
            return bool(os.read(self.fd, 4096))
        except BlockingIOError:
            return False


@pytest.fixture
def watched_log(tmp_path: Path) -> Iterator[tuple[Path, LogOpenProbe]]:
    if sys.platform != "linux":
        pytest.skip("The actual-open qualification probe requires Linux inotify")
    path = tmp_path / "unbound.log"
    path.write_text("UNBOUND_LOG_SENTINEL\n")
    probe = LogOpenProbe(path)
    try:
        yield path, probe
    finally:
        os.close(probe.fd)


def test_log_open_probe_detects_a_counterexample(watched_log: tuple[Path, LogOpenProbe]) -> None:
    path, probe = watched_log
    assert not probe.opened()
    assert path.read_text() == "UNBOUND_LOG_SENTINEL\n"
    assert probe.opened()


class TerminalProbe:
    def __init__(self, command: list[str], environment: dict[str, str], cwd: Path) -> None:
        self.master, slave = pty.openpty()
        termios.tcsetwinsize(slave, (36, 120))
        self.process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, env=environment, cwd=cwd)
        os.close(slave)
        self.screen = pyte.Screen(120, 36)
        self.stream = pyte.Stream(self.screen)
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.output = ""

    def shown(self) -> str:
        return "\n".join(self.screen.display)

    def pump(self) -> None:
        if select.select([self.master], [], [], 0.05)[0]:
            raw = os.read(self.master, 65536)
            if b"\x1b[6n" in raw:
                os.write(self.master, b"\x1b[1;1R")
            text = self.decoder.decode(raw)
            self.output += text
            self.stream.feed(text)

    def wait(self, predicate: Callable[[], bool]) -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if predicate():
                return
            self.pump()
        pytest.fail(f"Terminal expectation timed out:\n{self.shown()}")

    def colors(self) -> set[str]:
        return {color for line in self.screen.buffer.values() for cell in line.values() for color in (cell.fg, cell.bg)}

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)
        os.close(self.master)


@pytest.mark.parametrize("implementation", ["python", "native"])
@pytest.mark.parametrize("theme,no_color", [
    ("tokyo-night", None), ("nord", None), ("gruvbox", None),
    ("textual-light", None), ("unknown-theme", None), ("nord", ""), ("nord", "1"),
])
def test_installed_startup_theme_and_log_refusal(
    implementation: str, theme: str, no_color: str | None, tmp_path: Path,
    installed_entry: tuple[Path, dict[str, str]], watched_log: tuple[Path, LogOpenProbe],
) -> None:
    executable, environment = installed_entry
    binary = os.environ.get("TUI_NATIVE_TEST_BINARY")
    if implementation == "native" and not binary:
        pytest.skip("Set TUI_NATIVE_TEST_BINARY to a matching compiled native executable")
    if implementation == "native":
        assert binary is not None and os.access(binary, os.X_OK)
    requests: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def respond(self, body: Any) -> None:
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            requests.append((self.path, "GET"))
            self.respond({"api_version": "v1", "registry_digest": "fixture", "ops": [], "capabilities": {"streaming": False}})

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body.get("method", "")))
            if self.path == "/api/enhanced/helpers/list_skills":
                self.respond([])
                return
            self.respond({"jsonrpc": "2.0", "id": body.get("id"), "result": {
                "kind": "task", "id": "environment-task", "contextId": "environment-context",
                "status": {"state": "completed"},
                "artifacts": [{"parts": [{"kind": "text", "text": "Environment fixture ready"}]}],
            }})

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    path, probe = watched_log
    environment.update({"TERM": "xterm-256color", "COLORTERM": "truecolor", "TEXTUAL_ANIMATIONS": "none",
                        "AGENT_AUTH_MODE": "none", "AGENT_THEME": theme, "AGENT_LOG_FILE": str(path),
                        "AGENT_URL": f"http://127.0.0.1:{server.server_port}"})
    environment.pop("NO_COLOR", None)
    environment.pop("AGENT_TASK_ID", None)
    if no_color is not None:
        environment["NO_COLOR"] = no_color
    if implementation == "native":
        assert binary is not None
        command = [binary]
        environment["AGENT_TASK_ID"] = "environment-task"
    else:
        command = [str(executable), "--prompt", "Read fixture"]
    terminal = TerminalProbe(command, environment, tmp_path)
    try:
        terminal.wait(lambda: "Environment fixture ready" in terminal.shown())
        colors = terminal.colors()
        monochrome = all(color == "default" or len(color) == 6 and color[:2] == color[2:4] == color[4:] for color in colors)
        disabled = no_color is not None if implementation == "python" else bool(no_color)
        if disabled:
            assert monochrome, colors
        else:
            assert BACKGROUNDS[theme] in colors, colors
        os.write(terminal.master, b"\x16" if implementation == "python" else b"l")
        refusal = "authenticated host reader is required" if implementation == "python" else "Authenticated host access is required"
        terminal.wait(lambda: refusal in terminal.shown())
        assert "UNBOUND_LOG_SENTINEL" not in terminal.output
        assert not any(path.startswith("/host/logs") for path, _ in requests)
        assert not probe.opened()
        os.write(terminal.master, b"\x11" if implementation == "python" else b"q")
        assert terminal.process.wait(timeout=5) == 0
        assert not probe.opened()
    finally:
        terminal.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
