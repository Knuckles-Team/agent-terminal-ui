"""Actual native local-session composition, lifecycle and backpressure journeys."""

import json
import os
import signal
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.test_native_public_details_pty import NativeTerminal

pytestmark = [
    pytest.mark.spec("TUI-RUNTIME-R011.14"),
    pytest.mark.skipif(
        not os.environ.get("TUI_NATIVE_TEST_BINARY"),
        reason="Requires compiled native executable",
    ),
]

BACKEND = r"""
import json, os, sys, threading, time
fds = map(int, os.listdir("/proc/self/fd")) if os.path.isdir("/proc/self/fd") else range(3, 256)
assert not any(os.isatty(fd) for fd in fds if fd > 2), "Inherited terminal descriptor"
lock = threading.Lock()
active = threading.Event()
wire = os.environ["TUIG_TEST_WIRE"]
def send(value):
    with lock:
        print(json.dumps({"jsonrpc":"2.0", **value}), flush=True)
def update(text):
    send({"method":"session/update","params":{"sessionId":"local-session","update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":text}}}})
def reply(message, result):
    send({"id":message["id"],"result":result})
def turn(message, text, cancel):
    if text == "unknown":
        send({"id":999,"result":{"stopReason":"end_turn"}})
        return
    if text in ("hold", "flood"):
        if text == "flood":
            for index in range(1024):
                if cancel.is_set(): break
                update(str(index % 10) * 900 + "\n")
                time.sleep(.002)
        else:
            update("Waiting for cancellation")
        cancel.wait(10)
        reply(message, {"stopReason":"cancelled"})
    else:
        update("Partial ")
        time.sleep(.5 if text == "stream" else .05)
        update("reply: " + text + "\u001b]52;c;inert\u0007\u202e")
        reply(message, {"stopReason":"end_turn"})
with open(os.environ["TUIG_TEST_PID"], "w") as out: out.write(str(os.getpid()))
for line in sys.stdin:
    message = json.loads(line)
    with open(wire, "a") as out: out.write(json.dumps(message) + "\n")
    method = message["method"]
    if method == "initialize":
        assert message["params"]["clientCapabilities"] == {}
        capabilities = {"sessionCapabilities":{"close":{}}}
        reply(message, {"protocolVersion":1,"agentCapabilities":capabilities})
    elif method == "session/new": reply(message, {"sessionId":"local-session"})
    elif method == "session/prompt":
        assert message["params"]["sessionId"] == "local-session"
        active = threading.Event()
        text = message["params"]["prompt"][0]["text"]
        threading.Thread(target=turn, args=(message,text,active), daemon=True).start()
    elif method == "session/cancel": active.set()
    elif method == "session/close":
        active.set()
        reply(message, {})
        break
"""


@pytest.fixture
def local_terminal(tmp_path, monkeypatch):
    backend = tmp_path / "arbora-acp"
    backend.write_text(f"#!{sys.executable}\n{BACKEND}")
    backend.chmod(0o700)
    wire = tmp_path / "wire.jsonl"
    pid = tmp_path / "pid"
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("TUIG_TEST_WIRE", str(wire))
    monkeypatch.setenv("TUIG_TEST_PID", str(pid))
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    terminal = NativeTerminal(
        server,
        [],
        task_id=None,
        arguments=("--local-runtime", "--local-model", "test:model"),
    )
    try:
        terminal.wait_until(lambda: "Compose local turn" in terminal.shown())
        yield terminal, wire
    finally:
        if terminal.process.poll() is None:
            terminal.send(b"\x03")
            terminal.process.wait(timeout=10)
        terminal.close()
        server.server_close()
        if pid.exists():
            with pytest.raises(ProcessLookupError):
                os.kill(int(pid.read_text()), 0)


def messages(wire):
    return [json.loads(line) for line in wire.read_text().splitlines()]


def test_local_sequential_turns_are_bound_and_duplicate_enter_is_inert(local_terminal):
    terminal, wire = local_terminal
    terminal.send("first café\r\r\r".encode())
    terminal.wait_until(lambda: "Turn completed" in terminal.shown())
    assert "Partial reply: first café" in terminal.shown()
    terminal.send(b"psecond\r")
    terminal.wait_until(
        lambda: (
            "reply: second" in terminal.shown() and "Turn completed" in terminal.shown()
        )
    )
    terminal.quit()
    sent = messages(wire)
    prompts = [m for m in sent if m["method"] == "session/prompt"]
    assert [m["id"] for m in prompts] == [3, 4]
    assert [m["params"]["prompt"][0]["text"] for m in prompts] == [
        "first café",
        "second",
    ]
    assert sent[-1]["method"] == "session/close"
    assert sent[-1]["id"] == 5


@pytest.mark.parametrize("prompt", ["hold", "flood"])
def test_local_cancel_acknowledgement_allows_next_turn(local_terminal, prompt):
    terminal, wire = local_terminal
    terminal.send(prompt.encode() + b"\r")
    terminal.wait_until(
        lambda: any(m["method"] == "session/prompt" for m in messages(wire))
    )
    terminal.send(b"c")
    terminal.wait_until(lambda: "Turn canceled (acknowledged)" in terminal.shown())
    terminal.send(b"pafter cancel\r")
    terminal.wait_until(lambda: "reply: after cancel" in terminal.shown())
    terminal.quit()
    sent = messages(wire)
    assert [m["id"] for m in sent if m["method"] == "session/prompt"] == [3, 4]
    assert sum(m["method"] == "session/cancel" for m in sent) == 1


def test_local_unknown_outcome_closes_without_replay(local_terminal):
    terminal, wire = local_terminal
    terminal.send(b"unknown\r")
    terminal.wait_until(lambda: "Session closed:" in terminal.shown())
    terminal.send(b"p\r")
    terminal.send(b"q")
    assert terminal.process.wait(timeout=10) != 0
    assert sum(m["method"] == "session/prompt" for m in messages(wire)) == 1


@pytest.mark.parametrize("external", [False, True])
def test_local_quit_during_backpressure_cancels_and_restores_terminal(
    local_terminal, external
):
    terminal, wire = local_terminal
    terminal.send(b"flood\r")
    terminal.wait_until(
        lambda: any(m["method"] == "session/prompt" for m in messages(wire))
    )
    if external:
        terminal.process.send_signal(signal.SIGINT)
    else:
        terminal.send(b"\x03")
    assert terminal.process.wait(timeout=10) == 0
    termios = pytest.importorskip("termios")
    assert termios.tcgetattr(terminal.master) == terminal.original_terminal
    sent = messages(wire)
    assert any(m["method"] == "session/cancel" for m in sent)
    assert sent[-1]["method"] == "session/close"


def test_local_streamed_text_is_visible_before_turn_ack(local_terminal):
    terminal, wire = local_terminal
    terminal.send(b"stream\r")
    terminal.wait_until(lambda: "Partial " in terminal.shown())
    assert "Local turn running" in terminal.shown()
    terminal.resize(12, 40)
    terminal.wait_until(lambda: "Partial " in terminal.shown())
    terminal.resize(40, 100)
    terminal.wait_until(
        lambda: "Turn completed" in terminal.shown()
        and "Partial reply: stream" in terminal.shown()
    )
    terminal.quit()
    assert sum(m["method"] == "session/prompt" for m in messages(wire)) == 1


def test_local_terminal_output_backpressure_reaps_backend_without_reader(
    local_terminal,
):
    terminal, wire = local_terminal
    terminal.send(b"flood\r")
    terminal.wait_until(
        lambda: any(m["method"] == "session/prompt" for m in messages(wire))
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if any(m["method"] == "session/close" for m in messages(wire)):
            break
        time.sleep(0.02)
    assert any(m["method"] == "session/cancel" for m in messages(wire))
    assert any(m["method"] == "session/close" for m in messages(wire))
    terminal.process.wait(timeout=10)
    assert terminal.process.returncode != 0
    termios = pytest.importorskip("termios")
    assert termios.tcgetattr(terminal.master) == terminal.original_terminal
