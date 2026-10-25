"""Refresh documentation SVGs from the real Textual app and synthetic data.

Run from the repository root with ``python -m scripts.capture_screenshots``.
"""

import argparse
import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.client import AgentClient
from agent_terminal_ui.screens.settings import SettingsScreen
from agent_terminal_ui.settings import AppSettings
from agent_terminal_ui.tui.status_line import StatusLine
from agent_terminal_ui.widgets.conversation import Conversation
from agent_terminal_ui.widgets.tool_call_block import ToolCallBlock
from agent_terminal_ui.widgets.workflow import WorkflowSidebar

ASSET_DIR = Path(__file__).resolve().parents[1] / "docs/assets/screenshots"
CAPTURES = {
    "chat-wide.svg": (120, 36),
    "chat-compact.svg": (80, 30),
    "settings-wide.svg": (120, 36),
}


async def populate_chat(app: AgentApp) -> None:
    """Use the same conversation and workflow widgets as a live session."""
    conversation = app.query_one(Conversation)
    await conversation.clear_conversation()
    await conversation.add_info(
        "Documentation demo: synthetic session, no live service."
    )
    await conversation.add_user_message("Add parser coverage and summarize the result.")
    await conversation.add_agent_response(
        "I checked the parser and added focused tests for empty input "
        "and quoted values."
    )
    await conversation.add_tool_call(
        "shell",
        "pytest tests/test_parser.py -q",
        status="completed",
        call_id="demo-parser-tests",
        content="12 passed (synthetic demo output)",
    )
    await conversation.add_agent_response(
        "The demo checks passed. The changes are ready for review."
    )
    status = app.query_one(StatusLine)
    status.update_model("demo-model")
    workflow = app.query_one(WorkflowSidebar)
    for node in ("planner", "researcher", "verifier"):
        workflow.update_state(node, "completed")


async def capture_screenshots() -> dict[str, str]:
    """Render isolated demo views; never load an operator's settings or workspace."""
    result: dict[str, str] = {}
    client = AsyncMock(spec=AgentClient)
    client.base_url = "https://demo.invalid"
    client.list_skills.return_value = []
    client.list_capabilities.side_effect = RuntimeError("Offline documentation demo")
    with (
        TemporaryDirectory(prefix="tui-screenshots-") as temporary,
        patch.dict(os.environ, {"HOME": temporary}, clear=True),
        patch("agent_terminal_ui.app._iter_workspace_candidate_files", return_value=()),
        patch(
            "agent_terminal_ui.settings.load_agent_utilities_config", return_value={}
        ),
    ):
        for filename, size in CAPTURES.items():
            app = AgentApp(client=client, theme_name="tokyo-night")
            app.animation_level = "none"
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                await populate_chat(app)
                app.query_one(ToolCallBlock).expanded = True
                if filename == "chat-compact.svg":
                    await pilot.press("ctrl+b")
                if filename == "settings-wide.svg":
                    settings = AppSettings(Path(temporary) / "settings.toml")
                    await app.push_screen(SettingsScreen(settings))
                app.screen.set_focus(None)
                await pilot.pause()
                svg = app.export_screenshot(
                    title="Agent Terminal UI | Synthetic documentation demo"
                )
                result[filename] = (
                    "\n".join(line.rstrip() for line in svg.splitlines()) + "\n"
                )
    return result


def update_assets(assets: dict[str, str], output: Path, *, check: bool) -> list[str]:
    """Refresh managed assets, or return stale names without changing any files."""
    stale = []
    for filename, content in assets.items():
        destination = output / filename
        if destination.is_file() and destination.read_text(encoding="utf-8") == content:
            continue
        stale.append(filename)
        if not check:
            output.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
    return stale


def main() -> int:
    """Capture the fixed demo scenes and optionally check committed freshness."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail on stale assets.")
    parser.add_argument("--output", type=Path, default=ASSET_DIR)
    args = parser.parse_args()
    stale = update_assets(
        asyncio.run(capture_screenshots()), args.output, check=args.check
    )
    if args.check and stale:
        print("Stale screenshots: " + ", ".join(stale))
        print("Refresh with: uv run --frozen python -m scripts.capture_screenshots")
        return 1
    print("Screenshots are current." if args.check else "Screenshots refreshed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
