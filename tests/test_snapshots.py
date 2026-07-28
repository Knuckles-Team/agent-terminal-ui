"""Visual regression (golden) snapshots for UI uniformity.

Renders the conversation surface and its message-block widgets to SVG with
Textual and compares committed goldens with Syrupy. This catches
layout/contrast regressions across the built-in themes the UI ships with.
Regenerate goldens intentionally with ``pytest --snapshot-update``.
"""

from unittest.mock import AsyncMock

import pytest
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.image import SVGImageSnapshotExtension
from textual.app import App, ComposeResult

from agent_terminal_ui.tui.status_line import StatusLine
from agent_terminal_ui.widgets.conversation import Conversation

# Entrance animations are disabled in tests via pytest.ini (TEXTUAL_ANIMATIONS=none)
# so these goldens capture the resting state deterministically.

# Themes the UI is expected to render uniformly under (all Textual built-ins).
THEMES = ["tokyo-night", "nord", "gruvbox", "textual-light"]


class ConversationHarness(App):
    """Minimal host that mounts a Conversation populated with every block type."""

    def __init__(self, theme_name: str = "tokyo-night") -> None:
        super().__init__()
        self._theme_name = theme_name

    def compose(self) -> ComposeResult:
        yield Conversation()

    async def on_mount(self) -> None:
        self.theme = self._theme_name
        conv = self.query_one(Conversation)
        await conv.add_user_message("Refactor the parser and add tests")
        await conv.add_agent_response(
            "I'll start by reading the parser, then add coverage.", agent_name="main"
        )
        await conv.add_tool_call(
            tool_name="shell",
            tool_args='{"command": "pytest -q"}',
            call_id="t1",
        )
        await conv.add_info("Context compacted at L1 (tools summarized).")
        await conv.add_error("Connection to backend lost; retrying.")


class StatusLineHarness(App):
    """Host that mounts the StatusLine in isolation."""

    def compose(self) -> ComposeResult:
        yield StatusLine()


@pytest.fixture
def svg_snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Compare SVG output as one committed image per test case."""
    return snapshot.with_defaults(extension_class=SVGImageSnapshotExtension)


async def export_svg(app: App, *, terminal_size: tuple[int, int]) -> str:
    """Render an app at a fixed terminal size and export its settled SVG."""
    async with app.run_test(size=terminal_size) as pilot:
        await pilot.pause()
        return app.export_screenshot()


@pytest.mark.parametrize("theme", THEMES)
async def test_conversation_snapshot_per_theme(
    svg_snapshot: SnapshotAssertion, theme: str
) -> None:
    """The conversation surface renders uniformly under each built-in theme."""
    actual = await export_svg(
        ConversationHarness(theme_name=theme), terminal_size=(100, 32)
    )
    assert actual == svg_snapshot


async def test_status_line_snapshot(svg_snapshot: SnapshotAssertion) -> None:
    """The status line renders consistently."""
    actual = await export_svg(StatusLineHarness(), terminal_size=(100, 3))
    assert actual == svg_snapshot


async def test_main_screen_snapshot(svg_snapshot: SnapshotAssertion) -> None:
    """The full primary screen composes and renders without layout drift."""
    from agent_terminal_ui.app import AgentApp

    client = AsyncMock()
    client.base_url = "http://test.local"

    async def _empty_stream(*_a, **_k):
        for _ in ():
            yield _

    client.stream = _empty_stream
    actual = await export_svg(AgentApp(client=client), terminal_size=(120, 40))
    assert actual == svg_snapshot
