"""Exercise the sole native CLI with a scripted ACP subprocess, not an agent loop."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TUI_NATIVE_TEST_BINARY") or os.name != "posix",
    reason="Requires an explicitly built native executable and POSIX process signals",
)

BACKEND = r'''
import json, os, sys, time
from pathlib import Path

root = Path(os.environ["ACP_TEST_ROOT"])
(root / "pid").write_text(str(os.getpid()))
assert sys.argv[1:] == ["--local", "--model", "test:model", "--workspace-root", str(root)]
assert "AGENT_BEARER_TOKEN" not in os.environ
assert os.getcwd() == str(root)
mode = os.environ["ACP_TEST_MODE"]

def send(value):
    print(json.dumps(value), flush=True)

for line in sys.stdin:
    request = json.loads(line)
    with (root / "requests").open("a") as record:
        record.write(json.dumps(request) + "\n")
    method = request["method"]
    if method == "initialize":
        assert request["params"]["clientCapabilities"] == {}
        send({"jsonrpc":"2.0", "id":request["id"], "result":{"protocolVersion":1,"agentCapabilities":{"sessionCapabilities":{"close":{}}}}})
    elif method == "session/new":
        assert request["params"] == {"cwd":str(root),"mcpServers":[]}
        send({"jsonrpc":"2.0", "id":request["id"], "result":{"sessionId":"fixture-session"}})
    elif method == "session/prompt":
        assert request["params"] == {"sessionId":"fixture-session","prompt":[{"type":"text","text":"hello"}]}
        (root / "prompted").touch()
        if mode == "backpressure":
            send({"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"fixture-session","update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"x" * 100000}}}})
            (root / "output-sent").touch()
            continue
        if mode == "unresponsive":
            time.sleep(60)
        if mode == "cancel":
            continue
        if mode == "foreign":
            send({"jsonrpc":"2.0","id":999,"result":{"stopReason":"end_turn"}})
            continue
        send({"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"fixture-session","update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"native ACP reply\u001b[31m"}}}})
        send({"jsonrpc":"2.0","id":request["id"],"result":{"stopReason":"end_turn"}})
    elif method == "session/cancel":
        assert "id" not in request
        send({"jsonrpc":"2.0","id":3,"result":{"stopReason":"cancelled"}})
    elif method == "session/close":
        send({"jsonrpc":"2.0","id":request["id"],"result":{}})
    else:
        raise AssertionError(method)
'''


@pytest.mark.spec("TUI-RUNTIME-R011.14")
@pytest.mark.parametrize("mode", ["complete", "cancel", "foreign", "unresponsive", "backpressure"])
def test_native_acp_process_lifecycle(tmp_path, mode):
    backend = tmp_path / "arbora-acp"
    backend.write_text(f"#!{sys.executable}\n{BACKEND}")
    backend.chmod(0o700)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("AGENT_")}
    environment.update(
        PATH=f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}",
        ACP_TEST_ROOT=str(tmp_path),
        ACP_TEST_MODE=mode,
        AGENT_BEARER_TOKEN=os.urandom(16).hex(),
        AGENT_URL="invalid-central-endpoint-must-not-be-used",
    )
    process = subprocess.Popen(
        [os.environ["TUI_NATIVE_TEST_BINARY"], "--local-runtime", "--local-model", "test:model", "--headless", "--prompt", "hello"],
        cwd=tmp_path, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        if mode in {"cancel", "unresponsive", "backpressure"}:
            deadline = time.monotonic() + 10
            while not (tmp_path / "prompted").exists():
                assert process.poll() is None, "native CLI exited before prompt"
                assert time.monotonic() < deadline, "native CLI failed to prompt"
                time.sleep(0.02)
            if mode == "backpressure":
                while not (tmp_path / "output-sent").exists():
                    assert time.monotonic() < deadline, "backend did not send output"
                    time.sleep(0.02)
                time.sleep(0.1)
            process.send_signal(signal.SIGINT)
            if mode == "backpressure":
                # Do not drain stdout until cancellation and owned-child cleanup finish.
                process.wait(timeout=12)
        stdout, stderr = process.communicate(timeout=15)
        assert (process.returncode == 0) == (mode == "complete"), stderr
        assert "\x1b" not in stdout
        if mode == "complete":
            assert stdout == "native ACP reply[31m"
        elif mode == "backpressure":
            assert 0 < len(stdout) < 100000
        else:
            assert stdout == ""
        requests = [json.loads(line) for line in (tmp_path / "requests").read_text().splitlines()]
        assert [item["method"] for item in requests[:3]] == ["initialize", "session/new", "session/prompt"]
        assert sum(item["method"] == "session/prompt" for item in requests) == 1
        if mode in {"cancel", "foreign", "backpressure"}:
            assert any(item["method"] == "session/cancel" for item in requests)
        pid = int((tmp_path / "pid").read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if (tmp_path / "pid").exists():
            try:
                os.kill(int((tmp_path / "pid").read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass

SDK_BACKEND = r'''
import asyncio
import os
import acp
from acp import schema

class Fixture(acp.Agent):
    def on_connect(self, connection):
        self.connection = connection

    async def initialize(self, protocol_version, client_capabilities=None, **kwargs):
        assert protocol_version == 1
        assert not client_capabilities.terminal
        assert not client_capabilities.fs or not client_capabilities.fs.read_text_file
        return schema.InitializeResponse(protocol_version=1, agent_capabilities=schema.AgentCapabilities(
            load_session=False, session_capabilities=schema.SessionCapabilities(close=schema.SessionCloseCapabilities())))

    async def new_session(self, cwd, mcp_servers=None, **kwargs):
        assert cwd.startswith("/") and not mcp_servers
        return schema.NewSessionResponse(session_id="sdk-session")

    async def prompt(self, session_id, prompt, **kwargs):
        assert session_id == "sdk-session"
        assert len(prompt) == 1 and prompt[0].type == "text" and prompt[0].text == "hello"
        await self.connection.session_update(session_id, acp.update_agent_message_text("official SDK reply"))
        return schema.PromptResponse(stop_reason="end_turn")

    async def close_session(self, session_id, **kwargs):
        assert session_id == "sdk-session"
        return schema.CloseSessionResponse()

asyncio.run(acp.run_agent(Fixture(), use_unstable_protocol=os.environ["ACP_TEST_CLOSE_ENABLED"] == "true"))
'''


@pytest.mark.spec("TUI-RUNTIME-R011.14")
@pytest.mark.parametrize("close_enabled", [True, False])
def test_native_client_interoperates_with_official_python_acp_sdk(tmp_path, close_enabled):
    pytest.importorskip("acp", reason="Requires official agent-client-protocol 0.11.0 test SDK")
    backend = tmp_path / "arbora-acp"
    backend.write_text(f"#!{sys.executable}\n{SDK_BACKEND}")
    backend.chmod(0o700)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("AGENT_")}
    environment["ACP_TEST_CLOSE_ENABLED"] = str(close_enabled).lower()
    environment["PATH"] = f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"
    result = subprocess.run(
        [os.environ["TUI_NATIVE_TEST_BINARY"], "--local-runtime", "--local-model", "test:model", "--headless", "--prompt", "hello"],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=15,
    )
    assert (result.returncode == 0) == close_enabled, result.stderr
    assert result.stdout == "official SDK reply"
    if not close_enabled:
        assert "refused" in result.stderr
