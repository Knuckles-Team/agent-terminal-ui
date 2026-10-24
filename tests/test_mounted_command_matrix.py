"""Mounted client command evidence; legacy producer acceptance stays open."""

from contextlib import asynccontextmanager
from types import ModuleType
import sys
import json
from typing import Any
from io import StringIO
from rich.console import Console

import httpx
import pytest
from arbora.client._generated_models import REGISTRY_DIGEST

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.client import AgentClient
from agent_terminal_ui.commands import CommandProcessor
from agent_terminal_ui.tui.input_text_area import InputTextArea


@asynccontextmanager
async def mounted(reply):
    client = AgentClient(base_url="http://localhost:8000")
    await client._http_client.aclose()
    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as transport:
        client._http_client = transport
        app = AgentApp(client=client)
        async with app.run_test(size=(120, 35)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            yield app, pilot


async def submit(app, pilot, command):
    composer = app.screen.query_one(InputTextArea)
    composer.load_text(command)
    composer.focus()
    await pilot.press("enter")
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


def info(app):
    output = StringIO()
    console = Console(file=output, width=120, color_system=None)
    for widget in app.query(".info-message"):
        console.print(widget.content)
    return output.getvalue()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.4.2")
@pytest.mark.parametrize("command", ["/fleet", "/fleet status"])
@pytest.mark.parametrize(
    "value",
    [
        {"children": {"visible-child": {}}},
        {"children": {}},
        {"children": []},
        "UNAVAILABLE",
    ],
)
async def test_fleet_uses_served_status(command, value):
    requests = []

    def reply(request):
        requests.append((request.method, request.url.path))
        envelope = {
            "meta": {"registry_digest": REGISTRY_DIGEST},
            "ok": not isinstance(value, str),
        }
        if isinstance(value, str):
            envelope["error"] = {"code": value}
        else:
            envelope["result"] = {"value": value}
        return httpx.Response(200, json=envelope)

    async with mounted(reply) as (app, pilot):
        requests.clear()
        await submit(app, pilot, command)
        assert requests == [("POST", "/api/v1/ops/fleet.status")]
        rendered = info(app)
        if value == "UNAVAILABLE" or value == {"children": []}:
            assert "fleet.status unavailable" in rendered
            assert "UNAVAILABLE" in rendered or "INVALID_ENVELOPE" in rendered
        else:
            assert "Fleet status" in rendered
        assert "Pending approvals" not in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command,message",
    [
        ("/fleet grant approval-1", "web console"),
        ("/fleet nonsense", "Usage: /fleet [status]"),
        ("/fleet status extra", "Usage: /fleet [status]"),
        ("/skills", "skills.list"),
        ("/prompts", "prompts.list"),
        ("/kb", "kb.list"),
        ("/cron", "cron.calendar"),
        ("/pipeline", "pipeline.status"),
        ("/image missing.png", "not supported"),
        ("/bg task", "unavailable"),
        ("/attach session", "unavailable"),
        ("/mcp:reload", "unavailable"),
        ("/confirm unknown", "No pending PLAN"),
    ],
)
async def test_refusals_from_mounted_composer(command, message, monkeypatch):
    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(500)

    async with mounted(reply) as (app, pilot):
        requests.clear()
        notices = []
        original = app.notify

        def notify(text, **kwargs):
            notices.append(str(text))
            return original(text, **kwargs)

        monkeypatch.setattr(app, "notify", notify)
        await submit(app, pilot, command)
        assert any(message in notice for notice in notices), notices
        assert requests == []


@pytest.mark.asyncio
async def test_help_describes_registered_handlers_and_refusals(monkeypatch):
    registry = ModuleType("agent_utilities.messaging.commands")
    registry.__dict__["command_specs"] = lambda surface: [
        {"command": "fleet", "description": "stale external description"}
    ]
    monkeypatch.setitem(sys.modules, registry.__name__, registry)
    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(500)

    async with mounted(reply) as (app, pilot):
        requests.clear()
        await submit(app, pilot, "/help")
        rendered = info(app)
        for name in CommandProcessor(app).commands:
            assert f"/{name}" in rendered
        assert "stale external description" not in rendered
        assert "fleet.status" in rendered
        assert "skills.list" in rendered
        assert "unavailable" in rendered
        assert requests == []


LEGACY_CASES = [
    ("graph", "/api/enhanced/graph/stats"),
    ("memory", "/api/enhanced/graph/nodes"),
    ("ask question", "/api/graph/ask-data"),
    ("nl question", "/api/graph/nl-query"),
    ("obs up", "/api/graph/promql"),
    ("broker", "/api/graph/broker"),
    ("kvcache", "/api/graph/kvcache"),
    ("ingest -- fixture", "/api/enhanced/extract/submit"),
    ("sdd specs", "/api/enhanced/sdd/specs"),
    ("impact symbol", "/api/enhanced/graph/impact/symbol"),
    ("codemap fixture", "/api/codemap"),
    ("resources", "/api/enhanced/resources"),
    ("maintenance", "/api/enhanced/maintenance/status"),
    ("config", "/api/enhanced/config/backend"),
    ("model", "/models"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("command,path", LEGACY_CASES)
async def test_legacy_dependency_inventory(command, path):
    """Record unresolved routes, not successful served matrix acceptance."""
    requests = []

    def reply(request):
        requests.append(request.url.path)
        return httpx.Response(404, json={"detail": "No legacy route in fixture"})

    async with mounted(reply) as (app, pilot):
        requests.clear()
        await submit(app, pilot, f"/{command}")
        assert requests == [path]
        assert not app._is_processing


PROMPT_COMMANDS = [
    "plan",
    "chat",
    "build",
    "init",
    "review",
    "test",
    "search",
    "compact",
    "diff",
    "recap",
    "simplify",
    "add-dir",
    "goal",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("command", PROMPT_COMMANDS)
async def test_prompt_shortcut_submits_a_real_client_turn(command):
    methods = []

    def reply(request):
        if request.url.path == "/.well-known/agent-card.json":
            return httpx.Response(200, json={"capabilities": {"streaming": False}})
        if request.url.path == "/a2a":
            body = json.loads(request.content)
            methods.append(body["method"])
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "kind": "task",
                        "id": "matrix-task",
                        "contextId": "matrix-context",
                        "status": {"state": "completed"},
                        "artifacts": [
                            {"parts": [{"kind": "text", "text": "matrix answer"}]}
                        ],
                    },
                },
            )
        return httpx.Response(404)

    async with mounted(reply) as (app, pilot):
        await submit(app, pilot, f"/{command} fixture")
        assert methods == ["message/send"]
        assert not app._is_processing
        assert "matrix answer" in str(app.query_one("Conversation").transcript)


READ_CASES = [
    ("keybindings", ["/api/capabilities"], "CommandPalette"),
    (
        "mcp",
        ["/api/v1/ops/fleet.status", "/api/v1/ops/fleet.catalog.list"],
        "MCPScreen",
    ),
    ("tools", ["/api/v1/ops/fleet.catalog.list"], "MainScreen"),
    *[
        (name, ["/api/v1/ops/usage.read"], "UsageScreen")
        for name in ("usage", "stats", "cost", "context")
    ],
    ("history", ["/a2a"], "HistoryScreen"),
    *[
        (name, ["/api/capabilities"], "CapabilityPaletteScreen")
        for name in ("capability", "capabilities")
    ],
    *[(name, ["/api/runs"], "RunBrowserScreen") for name in ("run", "runs")],
    ("op fleet.status {}", ["/api/v1/ops/fleet.status"], "MainScreen"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("command,paths,screen", READ_CASES)
async def test_mounted_read_entry_points(command, paths, screen):
    requests = []

    def reply(request):
        path = request.url.path
        requests.append(path)
        if path == "/a2a":
            body = json.loads(request.content)
            assert body["method"] == "tasks/list"
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"tasks": [], "nextCursor": None},
                },
            )
        if path.startswith("/api/v1/ops/"):
            value: dict[str, Any] = (
                {"children": {}}
                if path.endswith("fleet.status")
                else {"items": [], "next_cursor": None}
                if path.endswith("fleet.catalog.list")
                else {"totals": {"tokens": 42}}
            )
            return httpx.Response(
                200,
                json={
                    "meta": {"registry_digest": REGISTRY_DIGEST},
                    "ok": True,
                    "result": {"value": value},
                },
            )
        if path == "/api/capabilities":
            return httpx.Response(
                200,
                json={
                    "schema_version": "1.0",
                    "catalog_version": "fixture",
                    "runtime": {},
                    "capabilities": [],
                },
            )
        if path == "/api/runs":
            return httpx.Response(
                200, json={"schema_version": "1.0", "count": 0, "runs": []}
            )
        return httpx.Response(404)

    async with mounted(reply) as (app, pilot):
        requests.clear()
        await submit(app, pilot, f"/{command}")
        assert requests == paths
        assert type(app.screen).__name__ == screen


LOCAL_COMMANDS = [
    "clear",
    "exit",
    "quit",
    "theme",
    "queue",
    "queue:clear",
    "queue:toggle",
    "export",
    "focus",
    "fast",
    "agents",
    "logs",
    "goal:status",
    "goal:cancel",
    "goal:history",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("command", LOCAL_COMMANDS)
async def test_local_entry_points_do_not_dispatch_network(command, monkeypatch):
    requests = []

    def reply(request):
        requests.append(request.url.path)
        return httpx.Response(404)

    async with mounted(reply) as (app, pilot):
        requests.clear()
        notices = []
        original = app.notify

        def notify(text, **kwargs):
            notices.append(str(text))
            return original(text, **kwargs)

        monkeypatch.setattr(app, "notify", notify)
        await submit(app, pilot, f"/{command}")
        assert requests == []
        assert not any("Error executing" in text for text in notices)
        if command in ("exit", "quit"):
            assert type(app.screen).__name__ == "ExitConfirmScreen"
        elif command == "queue:toggle":
            assert app._queue_enabled is False
        elif command == "export":
            assert "Nothing to export yet" in notices
        elif command == "focus":
            assert not app.screen.query_one("#sidebar").display


def test_inventory_accounts_for_every_registered_command():
    names = set(LOCAL_COMMANDS + PROMPT_COMMANDS)
    names.update(command.split()[0] for command, _ in LEGACY_CASES)
    names.update(command.split()[0] for command, _, _ in READ_CASES)
    names.update(
        "help fleet skills prompts kb cron pipeline image bg attach mcp:reload confirm".split()
    )
    assert names == set(CommandProcessor(object()).commands)
