"""Optional Python/native terminal presentation against one local task fixture."""

import codecs
import json
import os
import re
import select
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pty = pytest.importorskip("pty")
termios = pytest.importorskip("termios")
pyte = pytest.importorskip("pyte")

pytestmark = pytest.mark.spec("TUI-RUNTIME-R008")
REPLY = "\n\n".join(f"row-{index:03d} fixture" for index in range(120))


@pytest.mark.parametrize("implementation", ["python", "native"])
@pytest.mark.parametrize("no_color", [False, True])
def test_read_scroll_resize_theme_and_quit(
    implementation: str, no_color: bool, tmp_path: Path,
) -> None:
    binary = os.environ.get("TUI_NATIVE_TEST_BINARY")
    if implementation == "native" and not binary:
        pytest.skip("Set TUI_NATIVE_TEST_BINARY to a current compiled executable")
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def respond(self, body):
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self.respond({"api_version": "v1", "registry_digest": "fixture", "ops": [], "capabilities": {"streaming": False}})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body.get("method", self.path))
            if self.path == "/api/enhanced/helpers/list_skills":
                self.respond([])
                return
            self.respond({
                "jsonrpc": "2.0", "id": body.get("id"), "result": {
                    "kind": "task", "id": "presentation-task", "contextId": "presentation-context",
                    "status": {"state": "completed"},
                    "artifacts": [{"parts": [{"kind": "text", "text": REPLY}]}],
                },
            })

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    master, slave = pty.openpty()
    termios.tcsetwinsize(slave, (30, 100))
    environment = {
        **os.environ,
        "TERM": "xterm-256color", "COLORTERM": "truecolor",
        "AGENT_URL": f"http://127.0.0.1:{server.server_port}",
        "AGENT_AUTH_MODE": "none", "AGENT_THEME": "tokyo-night",
        "AGENT_UTILITIES_DATA_DIR": str(tmp_path / "data"),
        "AGENT_UTILITIES_CONFIG_DIR": str(tmp_path / "config"),
        "TEXTUAL_ANIMATIONS": "none",
        "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
    }
    environment.pop("AGENT_BEARER_TOKEN", None)
    environment.pop("NO_COLOR", None)
    environment.pop("AGENT_TASK_ID", None)
    if no_color:
        environment["NO_COLOR"] = "1"
    if implementation == "native":
        assert binary is not None
        environment["AGENT_TASK_ID"] = "presentation-task"
        command = [binary]
    else:
        command = [sys.executable, "-m", "agent_terminal_ui.terminal_ui", "--prompt", "Read fixture"]
    process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, env=environment)
    os.close(slave)
    screen = pyte.Screen(100, 30)
    stream = pyte.Stream(screen)
    decoder = codecs.getincrementaldecoder("utf-8")("replace")

    def shown():
        return "\n".join(screen.display)

    def pump():
        if select.select([master], [], [], 0.05)[0]:
            raw = os.read(master, 65536)
            if b"\x1b[6n" in raw:
                os.write(master, b"\x1b[1;1R")
            stream.feed(decoder.decode(raw))

    def wait_until(predicate):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if predicate():
                return
            pump()
        pytest.fail(f"Terminal expectation timed out:\n{shown()}\nMethods: {requests}")

    def monochrome():
        for line in screen.buffer.values():
            for cell in line.values():
                for color in (cell.fg, cell.bg):
                    if color == "default":
                        continue
                    if len(color) != 6 or not color[:2] == color[2:4] == color[4:]:
                        return False
        return True

    def settle():
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            pump()

    def page_up_from_end():
        os.write(master, b"\x1b[F")
        wait_until(lambda: ("Execution trace" if implementation == "python" else "quit") in shown())
        settle()
        before = shown()
        os.write(master, b"\x1b[5~")
        wait_until(lambda: shown() != before and "row-" in shown())
        settle()

    def colors():
        return {(cell.fg, cell.bg) for line in screen.buffer.values() for cell in line.values() if cell.data.strip()}

    try:
        wait_until(lambda: "row-" in shown())
        if implementation == "python":
            wait_until(lambda: "Execution trace" in shown())
            settle()
            os.write(master, b"\x02")
            settle()
            os.write(master, b"\x02")  # Reopen into the sidebar tab controls.
            settle()
            os.write(master, b"\x1b[C")
            wait_until(lambda: "Swarm" in shown())
            os.write(master, b"\x02")  # Return focus to the composer.
            settle()
            os.write(master, b"\x1b[19~")  # F8 focuses the conversation.
            settle()
        page_up_from_end()
        methods_before = list(requests)
        for columns, rows in [(40, 16), (100, 30)]:
            screen.resize(lines=rows, columns=columns)
            termios.tcsetwinsize(master, (rows, columns))
            process.send_signal(signal.SIGWINCH)
            settle()
            page_up_from_end()
        visible_rows = re.findall(r"row-\d{3}", shown())
        colors_before = colors()
        os.write(master, b"\x1bT" if implementation == "python" else b"\x1b[17~")
        if not no_color or implementation == "python":
            wait_until(lambda: colors() != colors_before)
        settle()
        assert re.findall(r"row-\d{3}", shown()) == visible_rows
        assert monochrome() is no_color
        if not no_color:
            assert colors() != colors_before
        assert requests == methods_before
        os.write(master, b"\x11" if implementation == "python" else b"q")
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        os.close(master)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
