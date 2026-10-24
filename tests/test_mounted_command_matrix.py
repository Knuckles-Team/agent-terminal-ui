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
        if screen in {"UsageScreen", "CapabilityPaletteScreen", "RunBrowserScreen"}:
            await pilot.press("escape")
            await pilot.pause()
            assert app.focused is app.screen.query_one(InputTextArea)
            await submit(app, pilot, "/help")
            assert "Available Commands" in info(app)
            assert requests == paths


LOCAL_COMMANDS = [
    "clear",
    "file",
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
        "help settings config resources maintenance fleet skills prompts kb cron pipeline image bg attach mcp:reload confirm".split()
    )
    assert names == set(CommandProcessor(object()).commands)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["denied", "timeout"])
@pytest.mark.parametrize(
    "command,path,status_selector",
    [
        ("fleet", "/api/v1/ops/fleet.status", None),
        ("mcp", "/api/v1/ops/fleet.status", "#mcp-status"),
        ("tools", "/api/v1/ops/fleet.catalog.list", None),
        ("history", "/a2a", "#history-reply"),
        ("usage", "/api/v1/ops/usage.read", "#usage-hist"),
        ("capabilities", "/api/capabilities", "#capability-palette-status"),
        ("run", "/api/runs", "#run-browser-status"),
    ],
)
async def test_supported_read_failure_keeps_composer_usable(
    failure, command, path, status_selector, monkeypatch
):
    requests = []

    def reply(request):
        requests.append(request.url.path)
        if failure == "timeout":
            raise httpx.ReadTimeout("fixture timeout", request=request)
        return httpx.Response(403, json={"detail": "fixture denied"})

    async with mounted(reply) as (app, pilot):
        requests.clear()
        notices = []
        original = app.notify

        def notify(text, **kwargs):
            notices.append(str(text))
            return original(text, **kwargs)

        monkeypatch.setattr(app, "notify", notify)
        await submit(app, pilot, f"/{command}")
        assert requests == [path]
        rendered = (
            str(app.screen.query_one(status_selector).render())
            if status_selector
            else info(app) + "\n".join(notices)
        )
        assert "unavailable" in rendered.lower()
        assert not any("Error executing" in notice for notice in notices)
        if status_selector:
            await pilot.press("escape")
            await pilot.pause()
        assert app.focused is app.screen.query_one(InputTextArea)
        await submit(app, pilot, "/help")
        assert "Available Commands" in info(app)
        assert requests == [path]
        assert not app._is_processing


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.4.3.1")
async def test_settings_command_edits_saved_settings_and_reopens(tmp_path, monkeypatch):
    from textual.widgets import Checkbox, Input
    from agent_terminal_ui import settings
    from agent_terminal_ui.screens.settings import SettingsScreen

    path = tmp_path / "settings.toml"
    monkeypatch.setattr(settings, "DEFAULT_SETTINGS_FILE", path)
    monkeypatch.setattr(settings, "load_agent_utilities_config", lambda: {})
    requests = []

    def reply(request):
        requests.append(request.url.path)
        return httpx.Response(404)

    async with mounted(reply) as (app, pilot):
        requests.clear()
        await submit(app, pilot, "/settings")
        assert isinstance(app.screen, SettingsScreen)
        search = app.screen.query_one("#settings-search", Input)
        search.focus()
        await pilot.press(*"sidebar", "tab", "tab")
        checkbox = app.focused
        assert isinstance(checkbox, Checkbox)
        previous = checkbox.value
        await pilot.press("space", "escape")
        await pilot.pause()
        assert app.focused is app.screen.query_one(InputTextArea)
        assert settings.AppSettings(path).get("sidebar_visible") is not previous
        await submit(app, pilot, "/settings")
        checkbox = next(
            w for w in app.screen.query(Checkbox) if w.name == "sidebar_visible"
        )
        assert checkbox.value is not previous
        await pilot.press("escape")
        await submit(app, pilot, "/help")
        assert "/settings" in info(app)
        assert requests == []


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.2.1")
@pytest.mark.parametrize("command", ["model", "model list", "model show"])
@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "denied",
        "timeout",
        "invalid-json",
        "non-object",
        "bad-models",
        "bad-cost",
        "bad-tags",
        "bad-input-cost",
        "bad-output-cost",
        "nonfinite-cost",
        "huge-cost",
        "bool-cost",
        "bad-tags-container",
    ],
)
async def test_model_read_failure_is_not_an_empty_registry(command, failure):
    requests = []

    def reply(request):
        requests.append(request.url.path)
        if failure == "timeout":
            raise httpx.ReadTimeout("fixture timeout", request=request)
        if failure == "invalid-json":
            return httpx.Response(200, content=b"invalid")
        if failure == "non-object":
            return httpx.Response(200, json=[])
        if failure == "bad-models":
            return httpx.Response(200, json={"models": ["invalid"]})
        malformed_fields: dict[str, dict[str, Any]] = {
            "bad-cost": {"cost": "bad"},
            "bad-tags": {"tags": [1]},
            "bad-input-cost": {"cost": {"input": "bad"}},
            "bad-output-cost": {"cost": {"output": None}},
            "nonfinite-cost": {"cost": {"input": float("nan")}},
            "huge-cost": {"cost": {"output": 10**400}},
            "bool-cost": {"cost": {"input": True}},
            "bad-tags-container": {"tags": "tag"},
        }
        if failure in malformed_fields:
            model = {"id": "x", **malformed_fields[failure]}
            return httpx.Response(
                200, content=json.dumps({"models": [model], "default_id": "x"})
            )
        return httpx.Response(404 if failure == "missing" else 403)

    async with mounted(reply) as (app, pilot):
        requests.clear()
        await submit(app, pilot, f"/{command}")
        rendered = info(app)
        assert "Model registry unavailable" in rendered
        assert "No models configured" not in rendered
        assert "No model details" not in rendered
        assert requests == ["/models"]


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.4.1")
@pytest.mark.parametrize(
    "command,route",
    [
        ("config", "/api/enhanced/config/backend"),
        ("config set token secret", "/api/enhanced/config/backend"),
        ("resources", "/api/enhanced/resources"),
        ("resources spawn {}", "/api/enhanced/resources"),
        ("maintenance", "/api/enhanced/maintenance"),
        ("maintenance run cleanup", "/api/enhanced/maintenance"),
    ],
)
async def test_legacy_management_refuses_before_dispatch(command, route, monkeypatch):
    requests = []

    def reply(request):
        requests.append(request.url.path)
        return httpx.Response(404)

    async with mounted(reply) as (app, pilot):
        requests.clear()
        notices = []
        monkeypatch.setattr(
            app, "notify", lambda message, **kwargs: notices.append(message)
        )
        await submit(app, pilot, f"/{command}")
        assert len(notices) == 1
        assert "unavailable" in notices[0]
        assert route in notices[0]
        assert requests == []


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.2.1")
@pytest.mark.parametrize(
    "models", [[], [{"id": "fixture-model", "name": "Fixture model"}]]
)
async def test_model_registry_empty_and_populated_remain_successful(models):
    requests = []

    def reply(request):
        requests.append(request.url.path)
        return httpx.Response(200, json={"models": models, "default_id": None})

    async with mounted(reply) as (app, pilot):
        requests.clear()
        await submit(app, pilot, "/model list")
        rendered = info(app)
        assert "Model registry unavailable" not in rendered
        assert ("No models configured" in rendered) is (not models)
        if models:
            assert "fixture-model" in rendered
        assert requests == ["/models"]


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R012.4.3.1")
@pytest.mark.parametrize("command", ["/focus", "/focus "])
async def test_focus_command_keeps_composer_and_sidebar_shortcut_keeps_navigation(
    command,
):
    requests = []

    def reply(request):
        requests.append(request.url.path)
        return httpx.Response(404)

    async with mounted(reply) as (app, pilot):
        requests.clear()
        composer = app.screen.query_one(InputTextArea)
        sidebar = app.screen.query_one("#sidebar")
        initially_visible = sidebar.display
        for visible in (not initially_visible, initially_visible):
            await submit(app, pilot, command)
            assert sidebar.display is visible
            assert app.focused is composer
            assert composer.text == ""
        await pilot.press("ctrl+b")
        await pilot.pause()
        assert not sidebar.display
        assert app.focused is composer
        await pilot.press("ctrl+b")
        await pilot.pause()
        assert sidebar.display
        assert app.focused is not None and sidebar in app.focused.ancestors
        assert requests == []
        assert not app._is_processing
