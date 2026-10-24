"""Opt-in proof of the built wheel's real installed console entry point."""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

@pytest.fixture
def installed_entry(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    configured = os.environ.get("TUI_TEST_INSTALLED_ENV")
    if not configured:
        pytest.skip("Set TUI_TEST_INSTALLED_ENV to an isolated installation of the current wheel")
    assert configured is not None
    environment = Path(configured)
    executable = environment / "bin/agent-terminal-ui"
    python = environment / "bin/python"
    child_env = {**os.environ, "AGENT_UTILITIES_DATA_DIR": str(tmp_path / "data"),
                 "AGENT_UTILITIES_CONFIG_DIR": str(tmp_path / "config"), "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        child_env.pop(key, None)
    child_env.pop("PYTHONPATH", None)
    child_env.pop("AGENT_BEARER_TOKEN", None)
    probe = subprocess.run([str(python), "-I", "-c", "import importlib.metadata as m, agent_terminal_ui; d=m.distribution('agent-terminal-ui'); print(next(e.value for e in d.entry_points if e.name=='agent-terminal-ui')); print(agent_terminal_ui.__file__)"], cwd=tmp_path, env=child_env, capture_output=True, text=True, timeout=20, check=True)
    target, module = probe.stdout.strip().splitlines()
    assert target == "agent_terminal_ui.terminal_ui:terminal_ui"
    assert Path(module).is_relative_to(environment)
    license_probe = subprocess.run([str(python), "-I", "-c", "from importlib.resources import files; print(files('agent_terminal_ui').joinpath('LICENSE').read_text(), end='')"], cwd=tmp_path, env=child_env, capture_output=True, text=True, timeout=20, check=True)
    assert license_probe.stdout == (Path(__file__).resolve().parents[1] / "agent_terminal_ui/LICENSE").read_text()
    return executable, child_env


@pytest.mark.spec("TUI-RUNTIME-R015.70")
def test_source_quality_entry_wiring(tmp_path: Path, installed_entry: tuple[Path, dict[str, str]]) -> None:
    executable, child_env = installed_entry
    methods: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def respond(self, value: dict[str, object]) -> None:
            raw = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            methods.append("GET")
            self.respond({"capabilities": {"streaming": False}})

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            methods.append(body["method"])
            self.respond({"jsonrpc": "2.0", "id": body["id"], "result": {
                "kind": "task", "id": "installed-task", "contextId": "installed-context",
                "status": {"state": "completed"},
                "artifacts": [{"parts": [{"kind": "text", "text": "Installed entry confirmed"}]}],
            }})

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    child_env["AGENT_URL"] = f"http://127.0.0.1:{server.server_port}"
    try:
        help_result = subprocess.run([str(executable), "--help"], cwd=tmp_path, env=child_env, capture_output=True, text=True, timeout=20)
        assert help_result.returncode == 0
        assert "--headless" in help_result.stdout and "--observe-task" in help_result.stdout
        invalid = subprocess.run([str(executable), "--headless"], cwd=tmp_path, env=child_env, capture_output=True, text=True, timeout=20)
        assert invalid.returncode == 2 and "--prompt" in invalid.stderr
        assert methods == []
        run = subprocess.run([str(executable), "--headless", "--prompt", "Read fixture"], cwd=tmp_path, env=child_env, capture_output=True, text=True, timeout=20)
        assert run.returncode == 0, run.stderr
        assert "Installed entry confirmed" in run.stdout
        assert methods.count("message/send") == 1
        assert all(method in {"GET", "message/send"} for method in methods)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.spec("TUI-RUNTIME-R015.71")
@pytest.mark.parametrize("credential,allowed", [(None, False), ("wrong-fixture-token", False), ("authorized-fixture-token", True)])
def test_installed_observer_distinguishes_denied_and_empty_reads(
    tmp_path: Path, installed_entry: tuple[Path, dict[str, str]],
    credential: str | None, allowed: bool,
) -> None:
    executable, child_env = installed_entry
    requests: list[tuple[str, str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body["method"], body["params"]))
            authorized = self.headers.get("Authorization") == "Bearer authorized-fixture-token"
            response = {"jsonrpc": "2.0", "id": body["id"], "result": {
                "kind": "task", "id": "empty-task", "contextId": "empty-context",
                "status": {"state": "completed"}, "artifacts": [],
            }} if authorized else {"error": "Fixture read denied"}
            raw = json.dumps(response).encode()
            self.send_response(200 if authorized else 403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    child_env["AGENT_URL"] = f"http://127.0.0.1:{server.server_port}"
    if credential is not None:
        child_env["AGENT_BEARER_TOKEN"] = credential
    try:
        result = subprocess.run([str(executable), "--observe-task", "empty-task"],
                                cwd=tmp_path, env=child_env, capture_output=True, text=True, timeout=20)
        output = result.stdout + result.stderr
        assert result.returncode == (0 if allowed else 1), output
        assert ("state: completed" in output) is allowed
        assert ("output: unavailable" in output) is allowed
        assert ("Task unavailable: read refused" in output) is not allowed
        assert "authorized-fixture-token" not in output
        assert "wrong-fixture-token" not in output
        assert requests == [("/a2a", "tasks/get", {"id": "empty-task"})]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
