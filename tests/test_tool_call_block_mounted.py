"""Mounted regressions for tool details, not just unmounted metadata."""

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Markdown, Static

from agent_terminal_ui.widgets.conversation import Conversation
from agent_terminal_ui.widgets.tool_call_block import (
    ToolCallBlock,
    ToolCallContent,
    ToolCallHeader,
)

pytestmark = pytest.mark.spec("TUI-RUNTIME-R012.1.4")


class ToolApp(App):
    def __init__(self, mode: str = "on-fail") -> None:
        super().__init__()
        self.settings = {"tool_expand": mode}

    def compose(self) -> ComposeResult:
        yield Conversation()


@pytest.mark.asyncio
async def test_tool_header_keyboard_and_mouse_preserve_choice_on_late_output():
    app = ToolApp()
    async with app.run_test() as pilot:
        conversation = app.query_one(Conversation)
        await conversation.add_tool_call("read_file", call_id="call-1")
        block = app.query_one(ToolCallBlock)
        header = block.query_one(ToolCallHeader)
        header.focus()
        await pilot.pause()
        assert app.focused is header
        await block.update_tool_call(content="first output")
        await pilot.pause()
        assert not block.expanded
        await pilot.press("enter")
        assert block.expanded
        assert block.query_one(ToolCallContent).display
        await pilot.press("space")
        assert not block.expanded
        await block.update_tool_call(
            status="failed",
            content="replacement output",
            details="[bold]literal[/bold]",
        )
        await pilot.pause()
        assert not block.expanded
        assert app.focused is header
        assert len(block.query(Markdown)) == 1
        assert block.query_one(Markdown)._markdown == "replacement output"
        assert (
            str(block.query_one(".tool-details", Static).render())
            == "[bold]literal[/bold]"
        )
        await pilot.click(ToolCallHeader)
        assert block.expanded
        assert block.query_one(ToolCallContent).display


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,status,expanded",
    [
        ("never", "failed", False),
        ("on-fail", "completed", False),
        ("on-fail", "failed", True),
        ("on-success", "completed", True),
        ("on-success", "failed", False),
        ("always", "in_progress", True),
    ],
)
async def test_tool_expansion_setting_applies_to_late_output(mode, status, expanded):
    app = ToolApp(mode)
    async with app.run_test() as pilot:
        conversation = app.query_one(Conversation)
        await conversation.add_tool_call("tool", call_id="call")
        await conversation.update_tool_call("call", status=status, content="output")
        await pilot.pause()
        block = app.query_one(ToolCallBlock)
        assert block.expanded is expanded
        assert block.query_one(Markdown)._markdown == "output"


@pytest.mark.asyncio
async def test_duplicate_tool_call_updates_one_widget_and_empty_content_clears():
    app = ToolApp("never")
    async with app.run_test() as pilot:
        conversation = app.query_one(Conversation)
        await conversation.add_tool_call("tool", call_id="call", content="initial")
        block = app.query_one(ToolCallBlock)
        await pilot.pause()
        await pilot.click(ToolCallHeader)
        assert block.expanded
        await conversation.add_tool_call(
            "tool", call_id="call", status="completed", content="replacement"
        )
        await pilot.pause()
        assert len(app.query(ToolCallBlock)) == 1
        assert block.expanded
        assert block.query_one(Markdown)._markdown == "replacement"
        await conversation.update_tool_call("call", content="", details="")
        await pilot.pause()
        assert not block.has_content
        assert block.query_one(Markdown)._markdown == ""
        assert not block.query_one(Markdown).display


@pytest.mark.asyncio
async def test_initial_failed_output_honors_policy_and_untrusted_header_is_literal():
    app = ToolApp()
    async with app.run_test() as pilot:
        await app.query_one(Conversation).add_tool_call(
            "[bold]tool[/bold]\x1b\x07\u202e",
            "[red]argument[/red]",
            call_id="call",
            agent_name="[blue]worker[/blue]",
            status="failed",
            content="output\x1b\u2066",
            details="[bold]details[/bold]\x07\u202e",
        )
        await pilot.pause()
        block = app.query_one(ToolCallBlock)
        assert block.expanded
        assert "[bold]tool[/bold]" in block.query_one(ToolCallHeader).render().plain
        assert "[blue]worker[/blue]" in block.query_one(ToolCallHeader).render().plain
        assert block.query_one(Markdown)._markdown == "output"
        assert (
            str(block.query_one(".tool-details", Static).render())
            == "[bold]details[/bold]"
        )
