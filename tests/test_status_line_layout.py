"""Supporting visible-layout regressions for TUI-RUNTIME-R012.6.2."""

import pytest
from textual.widgets import Footer, Static

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.tui.input_text_area import InputTextArea
from agent_terminal_ui.tui.status_line import StatusLine

pytestmark = pytest.mark.asyncio
UNAVAILABLE = "usage unavailable"


@pytest.mark.parametrize("processing", [False, True])
async def test_status_usage_is_visible_without_covering_composer(
    app: AgentApp, processing: bool
) -> None:
    async with app.run_test(size=(120, 35)) as pilot:
        status = app.query_one(StatusLine)
        widget = status.query_one("#status-tokens", Static)
        composer = app.query_one(InputTextArea)
        composer.load_text("draft prompt")
        composer.focus()
        status.set_thinking(processing)
        status.update_model("a-very-long-model-name")
        for width, height in [(120, 35), (80, 24), (60, 20), (40, 12), (120, 35)]:
            await pilot.resize_terminal(width, height)
            for usage, expected in [
                ({}, UNAVAILABLE),
                ({"total_tokens": 0, "estimated_cost_usd": 0}, "0 tokens ($0.0000)"),
                ({"total_tokens": None, "estimated_cost_usd": None}, UNAVAILABLE),
            ]:
                status.update_usage(usage)
                await pilot.pause()
                region = widget.content_region
                assert app.screen.region.contains_region(region)
                captured = "".join(
                    strip.crop(region.x, region.right).text
                    for strip in app.screen._compositor.render_strips()[
                        region.y : region.bottom
                    ]
                )
                assert "".join(captured.split()) == "".join(expected.split())
                main = app.query_one("#main-content")
                prompt = app.query_one("#prompt-container")
                footer = app.query_one(Footer)
                assert main.region.height > 0
                assert main.region.bottom <= prompt.region.y
                assert prompt.region.bottom <= status.region.y
                assert status.region.bottom <= footer.region.y
                assert app.screen.region.contains_region(footer.region)
                assert composer.has_focus
                assert composer.text == "draft prompt"


async def test_status_layout_preserves_sidebar_and_open_logs(app: AgentApp) -> None:
    async with app.run_test(size=(120, 35)) as pilot:
        status = app.query_one(StatusLine)
        status.set_thinking(True)
        composer = app.query_one(InputTextArea)
        composer.load_text("draft prompt")
        for width, height in [(120, 35), (80, 24), (60, 20)]:
            await pilot.resize_terminal(width, height)
            for sidebar_visible in [False, True]:
                await pilot.press("ctrl+b")
                assert app.query_one("#sidebar").display is sidebar_visible
                focused = app.focused
                await pilot.press("ctrl+v")
                await pilot.pause()
                log = app.query_one("#server-log")
                main = app.query_one("#main-content")
                prompt = app.query_one("#prompt-container")
                footer = app.query_one(Footer)
                assert log.display
                assert log.region.bottom <= main.region.y
                assert main.region.height > 0
                assert main.region.bottom <= prompt.region.y
                assert prompt.region.bottom <= status.region.y
                assert status.region.bottom <= footer.region.y
                assert app.screen.region.contains_region(footer.region)
                assert app.focused is focused
                assert composer.text == "draft prompt"
                await pilot.press("ctrl+v")
                await pilot.pause()
                assert not log.display
                assert main.region.height > 0
