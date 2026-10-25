"""Capture the compiled tuig terminal; Python is development tooling only."""

import argparse
import hashlib
import json
import os
import re
import sys
import threading
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_native_public_details_pty import NativeTerminal

ANSWER = (
    "Synthetic demo: compare two options, then join their results.\n"
    "The answer stays visible while public details are folded.\n"
    "No live provider or backend is connected."
)


def cell_color(value: str, default: str) -> str:
    if value == "default":
        return default
    if not re.fullmatch(r"[0-9a-f]{6}", value):
        raise ValueError(f"Gallery requires truecolor cells, got {value!r}")
    return "#" + value


def terminal_svg(screen, title: str) -> str:
    """Serialize actual terminal cells, including inverse selection and colors."""
    width, height = screen.columns * 9, screen.lines * 18
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">',
        f"<title>{escape(title)} — native tuig, synthetic fixture</title>",
        "<desc>Actual compiled Rust terminal output captured through a PTY. "
        "SVG cell rendering, not a desktop screenshot or live backend.</desc>",
        '<g font-family="DejaVu Sans Mono, monospace" font-size="15">',
    ]
    background = screen.buffer[0][0].bg
    background = cell_color(background, "#1a1b26")
    parts.append(f'<rect width="{width}" height="{height}" fill="{background}"/>')
    glyphs = []
    for row in range(screen.lines):
        for column in range(screen.columns):
            cell = screen.buffer[row][column]
            fg = cell_color(cell.fg, "#c0caf5")
            bg = cell_color(cell.bg, "#1a1b26")
            if cell.reverse:
                fg, bg = bg, fg
            x, y = column * 9, row * 18
            if bg != background:
                parts.append(
                    f'<rect x="{x}" y="{y}" width="9" height="18" fill="{bg}"/>'
                )
            if cell.data.strip():
                weight = ' font-weight="bold"' if cell.bold else ""
                glyphs.append(
                    f'<text x="{x}" y="{y + 14}" fill="{fg}"{weight}>'
                    f"{escape(cell.data)}</text>"
                )
    return "\n".join([*parts, *glyphs, "</g>", "</svg>", ""])


def capture(binary: Path, output: Path, source_revision: str) -> dict:
    """Serve only synthetic read fixtures to a real, explicitly supplied binary."""
    fixtures = ROOT / "tests/fixtures"
    graph = json.loads((fixtures / "execution_graph_contract.json").read_text())[
        "value"
    ]
    events = json.loads((fixtures / "public_run_events.json").read_text())
    events["run_id"] = graph["run_id"]
    for event in events["events"]:
        event["run_id"] = graph["run_id"]
    requests: list[tuple[str, dict[str, Any] | None, str | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def respond(self, body, status=200):
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            requests.append((self.path, None, self.headers.get("Authorization")))
            if self.path != "/api/v1/registry":
                self.respond({"error": "unexpected route"}, 404)
                return
            self.respond(
                {
                    "api_version": "v1",
                    "registry_digest": "gallery-fixture",
                    "ops": [{"id": "runs.events"}, {"id": "runs.execution_graph"}],
                }
            )

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body, self.headers.get("Authorization")))
            if self.path == "/a2a" and body.get("method") == "tasks/get":
                self.respond(
                    {
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "result": {
                            "kind": "task",
                            "id": graph["task_id"],
                            "contextId": "gallery-context",
                            "status": {"state": "completed"},
                            "metadata": {"arbora": {"runId": graph["run_id"]}},
                            "artifacts": [
                                {"parts": [{"kind": "text", "text": ANSWER}]}
                            ],
                        },
                    }
                )
            elif self.path in (
                "/api/v1/ops/runs.events",
                "/api/v1/ops/runs.execution_graph",
            ):
                value = events if self.path.endswith("runs.events") else graph
                self.respond(
                    {
                        "ok": True,
                        "meta": {
                            "api_version": "v1",
                            "registry_digest": "gallery-fixture",
                        },
                        "result": {"value": value},
                    }
                )
            else:
                self.respond({"error": "unavailable in synthetic fixture"}, 404)

        def log_message(self, *_args):
            pass

    output.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {
        "format": "native-pty-cell-svg-v1",
        "synthetic": True,
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "binary_source_revision": source_revision,
        "theme": "canopy",
        "columns": 100,
        "rows": 40,
        "screens": [],
        "fixtures": {
            name: hashlib.sha256((fixtures / name).read_bytes()).hexdigest()
            for name in ("execution_graph_contract.json", "public_run_events.json")
        },
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("AGENT_")
    }
    environment.update(
        TUI_NATIVE_TEST_BINARY=str(binary.resolve()), AGENT_THEME="canopy"
    )
    terminal = None
    try:
        with patch.dict(os.environ, environment, clear=True):
            terminal = NativeTerminal(
                server, requests, graph["task_id"], no_color=False
            )
        shown = terminal.shown

        def save(name, title, expected):
            terminal.wait_until(
                lambda: (
                    all(text in shown() for text in expected)
                    and "Reading run..." not in shown()
                )
            )
            svg = terminal_svg(terminal.screen, title)
            (output / f"{name}.svg").write_text(svg)
            receipt["screens"].append(
                {
                    "file": f"{name}.svg",
                    "title": title,
                    "sha256": hashlib.sha256(svg.encode()).hexdigest(),
                    "expected_text": expected,
                }
            )

        save(
            "answer",
            "Answer with folded public details",
            ["Synthetic demo:", "Execution trace"],
        )
        terminal.send(b"\t\r")
        save("public-summary", "Expanded public model summary", ["Public explanation:"])
        terminal.send(b"\t\r")
        save(
            "execution-trace",
            "Expanded public execution trace",
            ["task_started", "Public explanation:"],
        )
        terminal.send(b"i")
        save(
            "run-inspector",
            "Read-only inspector with unavailable operations",
            ["Run inspector (read-only)", "unavailable"],
        )
        terminal.send(b"g")
        save("graph-list", "Execution graph list", ["> 1. first [running]"])
        terminal.send(b"v\x1b[Z")
        save(
            "spatial-map",
            "Spatial dependency map with join selected",
            ["Selected 4: join [unobserved]", "Predecessors: 2, 3"],
        )
        terminal.quit()
        assert all(auth is None for _, _, auth in requests)
        assert all(
            body is None
            or path.startswith("/api/v1/ops/runs.")
            or body.get("method") == "tasks/get"
            for path, body, _ in requests
        )
        receipt["requests"] = [
            {"path": path, "method": body.get("method") if body else None}
            for path, body, _ in requests
        ]
        (output / "manifest.json").write_text(json.dumps(receipt, indent=2) + "\n")
        return receipt
    finally:
        if terminal is not None:
            terminal.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/assets/native")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_revision):
        parser.error("--source-revision must be the binary source commit SHA")
    capture(args.binary, args.output, args.source_revision)


if __name__ == "__main__":
    main()
