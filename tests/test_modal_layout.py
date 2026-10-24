"""Viewport and focus regressions for live modal layouts."""

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Button, Input, RichLog

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.tui.chat_modal import ChatModal
from agent_terminal_ui.tui.tool_approval_screen import ToolApprovalScreen

pytestmark = pytest.mark.spec("TUI-RUNTIME-R008")
SIZES = [(120, 40), (40, 12), (60, 20), (120, 40)]


@pytest.mark.asyncio
async def test_chat_dialog_remains_visible_and_closable_after_resize(
    fake_client: AsyncMock,
) -> None:
    app = AgentApp(client=fake_client)
    async with app.run_test(size=SIZES[0]) as pilot:
        await app.push_screen(ChatModal(
            "Agent communication", [{"sender": "agent", "content": "message"}]
        ))
        screen = app.screen
        close = screen.query_one("#close-btn", Button)
        close.focus()
        for width, height in SIZES:
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            assert screen.region.contains_region(screen.query_one("#chat-dialog").region)
            assert screen.region.contains_region(close.region)
            assert screen.query_one(RichLog).content_region.height >= 1
            assert app.focused is close
        await pilot.click(close)
        assert app.screen is not screen


@dataclass
class ToolEvent:
    call_id: str
    name: str = "read"
    arguments: str = "{}"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_count", [1, 20])
async def test_approval_feedback_and_last_tool_remain_reachable_after_resize(
    fake_client: AsyncMock, tool_count: int,
) -> None:
    app = AgentApp(client=fake_client)
    async with app.run_test(size=SIZES[0]) as pilot:
        await app.push_screen(ToolApprovalScreen({
            f"c{i}": ToolEvent(f"c{i}") for i in range(tool_count)
        }))
        screen = app.screen
        assert isinstance(screen, ToolApprovalScreen)
        feedback = screen.query_one("#feedback-input", Input)
        feedback.value = "Keep this feedback"
        feedback.focus()
        for width, height in SIZES:
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            dialog = screen.query_one("#approval-dialog")
            assert screen.region.contains_region(dialog.region)
            assert dialog.content_region.contains_region(feedback.region)
            assert app.focused is feedback
            assert feedback.value == "Keep this feedback"
            tools = screen.query_one("#tool-list", VerticalScroll)
            assert tools.content_region.height >= 1
            last = screen.query_one(f"#reject-c{tool_count - 1}", Button)
            last.focus()
            await pilot.pause()
            assert tools.content_region.contains_region(last.region)
            assert last.content_region.height == 1
            assert screen._decisions == {}
            feedback.focus()
            await pilot.pause()
        last.focus()
        await pilot.pause()
        await pilot.click(last)
        assert screen._decisions == {f"c{tool_count - 1}": "deny"}
        if tool_count > 1:
            assert last.content_region.height == 1
