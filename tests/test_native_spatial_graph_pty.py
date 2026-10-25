"""The optional spatial view uses the real native entry and validated fixture."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from tests.test_native_public_details_pty import NativeTerminal

pytestmark = [
    pytest.mark.spec(
        "TUI-RUNTIME-R008.3",
        "TUI-RUNTIME-R008.3.1",
        "TUI-RUNTIME-R010.12.1",
        "TUI-RUNTIME-R010.12.1.1",
        "TUI-RUNTIME-R010.12.1.2",
    ),
    pytest.mark.skipif(
        not os.environ.get("TUI_NATIVE_TEST_BINARY"),
        reason="Set TUI_NATIVE_TEST_BINARY to the current compiled executable",
    ),
]


# spec: TUI-RUNTIME-R010.12.1.2
@pytest.mark.parametrize("no_color", [False, True])
def test_native_spatial_map_theme_navigation_search_and_denial(
    no_color: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_THEME", "canopy")
    value = json.loads(
        (
            Path(__file__).parents[0] / "fixtures/execution_graph_contract.json"
        ).read_text()
    )["value"]
    requests: list[tuple[str, dict[str, Any] | None, str | None]] = []
    deny = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def respond(self, body: dict[str, Any], status: int = 200) -> None:
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            requests.append((self.path, None, self.headers.get("Authorization")))
            self.respond(
                {
                    "api_version": "v1",
                    "registry_digest": "map-fixture",
                    "ops": [{"id": "runs.execution_graph"}],
                }
            )

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body, self.headers.get("Authorization")))
            if self.path == "/a2a" and body.get("method") == "tasks/get":
                self.respond(
                    {
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "result": {
                            "kind": "task",
                            "id": value["task_id"],
                            "contextId": "map-context",
                            "status": {"state": "completed"},
                            "metadata": {"arbora": {"runId": value["run_id"]}},
                            "artifacts": [
                                {"parts": [{"kind": "text", "text": "Bound map task"}]}
                            ],
                        },
                    }
                )
            elif self.path == "/api/v1/ops/runs.execution_graph":
                if deny.is_set():
                    self.respond({"error": "denied"}, 403)
                else:
                    self.respond(
                        {
                            "ok": True,
                            "meta": {
                                "api_version": "v1",
                                "registry_digest": "map-fixture",
                            },
                            "result": {"value": value},
                        }
                    )
            else:
                self.respond({"error": "unavailable"}, 404)

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    terminal = NativeTerminal(server, requests, value["task_id"], no_color=no_color)
    shown, wait_until = terminal.shown, terminal.wait_until

    def assert_palette() -> None:
        background = "default" if no_color else "121c17"
        stone = "default" if no_color else "f1f5eb"
        sage = "default" if no_color else "adc99f"
        probes = [(0, 0, sage), (0, 1, sage), (1, 1, stone)]
        wait_until(
            lambda: all(
                terminal.screen.buffer[row][column].fg == foreground
                and terminal.screen.buffer[row][column].bg == background
                for row, column, foreground in probes
            )
        )
        if no_color:
            assert all(
                cell.fg == "default" and cell.bg == "default"
                for line in terminal.screen.buffer.values()
                for cell in line.values()
            )

    def capture_screen(stage: str) -> None:
        cells = [
            cell for line in terminal.screen.buffer.values() for cell in line.values()
        ]
        evidence = {
            "mode": "no-color" if no_color else "canopy",
            "stage": stage,
            "columns": terminal.screen.columns,
            "lines": terminal.screen.lines,
            "foregrounds": sorted({cell.fg for cell in cells}),
            "backgrounds": sorted({cell.bg for cell in cells}),
            "palette_probes": {
                name: {
                    "glyph": terminal.screen.buffer[row][column].data,
                    "foreground": terminal.screen.buffer[row][column].fg,
                    "background": terminal.screen.buffer[row][column].bg,
                }
                for name, row, column in [
                    ("border", 0, 0),
                    ("title", 0, 1),
                    ("body", 1, 1),
                ]
            },
            "reversed_cells": sum(cell.reverse for cell in cells),
            "screen": shown(),
        }
        print("TUI_SPATIAL_SCREEN " + json.dumps(evidence, ensure_ascii=False))

    try:
        wait_until(lambda: "Bound map task" in shown())
        assert_palette()
        terminal.send(b"i")
        wait_until(
            lambda: "Run inspector (read-only)" in shown() and "unavailable" in shown()
        )
        assert_palette()
        terminal.send(b"g")
        wait_until(lambda: "> 1. first [running]" in shown())
        terminal.send(b"v")
        wait_until(lambda: "Selected 1: first [running]" in shown())
        assert_palette()
        assert "selected edges" in shown()
        assert "Plan-step depends_on: predecessor -> dependent" in shown()
        before = list(requests)
        colors = {
            cell.bg
            for line in terminal.screen.buffer.values()
            for cell in line.values()
        }
        assert ("121c17" in colors) is not no_color
        capture_screen("selected-first")
        terminal.send(b"\x1b[Z")
        wait_until(lambda: "Selected 4: join [unobserved]" in shown())
        assert "Predecessors: 2, 3 | Dependents: none" in shown()
        capture_screen("selected-join")
        terminal.send(b"\x1b[17~")  # F6 cycles Canopy back to the unchanged default.
        if not no_color:
            wait_until(
                lambda: any(
                    cell.bg == "1a1b26"
                    for line in terminal.screen.buffer.values()
                    for cell in line.values()
                )
            )
        terminal.resize(16, 40)
        wait_until(lambda: "4. join [unobserved]" in shown())
        assert "Run inspector (read-only)" in shown()
        terminal.resize(24, 72)
        wait_until(lambda: "Selected 4: join [unobserved]" in shown())
        focused = shown()
        terminal.send(b"\x1b[D" * 3)
        wait_until(lambda: shown() != focused)
        terminal.send(b"\x1b[H")
        wait_until(lambda: shown() == focused)
        terminal.send(b"\x06Predecessors")
        wait_until(lambda: "Find: Predecessors" in shown())
        assert "Predecessors (depends_on): 2: left, 3: right" in shown()
        terminal.send(b"\x1b")
        wait_until(lambda: "Selected 4: join [unobserved]" in shown())
        terminal.send(b"v")
        wait_until(lambda: "> 4. join [unobserved]" in shown())
        terminal.send(b"v")
        wait_until(lambda: "Selected 4: join [unobserved]" in shown())
        terminal.send(b"xy \r")
        terminal.send(b"\t")
        wait_until(lambda: "Selected 1: first [running]" in shown())
        assert requests == before
        if no_color:
            assert all(
                cell.fg == "default" and cell.bg == "default"
                for line in terminal.screen.buffer.values()
                for cell in line.values()
            )
        deny.set()
        terminal.send(b"r")
        wait_until(lambda: "Execution graph denied; protected data cleared" in shown())
        assert "join" not in shown() and "first [running]" not in shown()
        assert (
            sum(path == "/api/v1/ops/runs.execution_graph" for path, _, _ in requests)
            == 2
        )
        assert all(auth is None for _, _, auth in requests)
        assert not any(
            body and body.get("method") in {"message/send", "tasks/cancel"}
            for _, body, _ in requests
        )
        terminal.quit()
    finally:
        terminal.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
