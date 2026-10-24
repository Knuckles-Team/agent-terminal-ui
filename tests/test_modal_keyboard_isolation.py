"""Mounted modal keyboard journeys and composer shortcut isolation."""

from unittest.mock import AsyncMock

import pytest
from textual.widgets import Input

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.tui.chat_modal import ChatModal
from agent_terminal_ui.tui.exit_confirm_screen import ExitConfirmScreen
from agent_terminal_ui.tui.input_text_area import InputTextArea
from agent_terminal_ui.tui.tool_approval_screen import ToolApprovalResult, ToolApprovalScreen
from agent_terminal_ui.widgets.graph_tree import GraphTree

pytestmark = pytest.mark.spec("TUI-RUNTIME-R008")


@pytest.mark.asyncio
async def test_exit_modal_reverse_tab_and_escape_restore_composer(fake_client: AsyncMock) -> None:
    app = AgentApp(client=fake_client)
    async with app.run_test() as pilot:
        composer = app.screen.query_one(InputTextArea)
        composer.load_text("Unfinished prompt")
        mode = app._agent_mode
        await pilot.press("ctrl+d")
        assert isinstance(app.screen, ExitConfirmScreen)
        assert app.focused is app.screen.query_one("#no")
        await pilot.press("shift+tab")
        assert app.focused is app.screen.query_one("#yes")
        assert app._agent_mode == mode
        await pilot.press("escape")
        assert not isinstance(app.screen, ExitConfirmScreen)
        assert app.focused is composer
        assert composer.text == "Unfinished prompt"


@pytest.mark.asyncio
async def test_graph_chat_escape_restores_composer(fake_client: AsyncMock) -> None:
    app = AgentApp(client=fake_client)
    async with app.run_test() as pilot:
        composer = app.screen.query_one(InputTextArea)
        composer.load_text("Unfinished prompt")
        app.on_graph_tree_node_clicked(GraphTree.NodeClicked({
            "title": "Subgraph chat", "messages": [{"sender": "agent", "content": "hello"}]
        }))
        await pilot.pause()
        assert isinstance(app.screen, ChatModal)
        await pilot.press("escape")
        assert not isinstance(app.screen, ChatModal)
        assert app.focused is composer
        assert composer.text == "Unfinished prompt"


@pytest.mark.asyncio
async def test_approval_input_owns_editing_keys_and_escape_denies(
    fake_client: AsyncMock, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = AgentApp(client=fake_client)
    results: list[ToolApprovalResult] = []
    monkeypatch.setattr(app, "_handle_tool_approval_result", results.append)
    async with app.run_test() as pilot:
        composer = app.screen.query_one(InputTextArea)
        composer.load_text("Unfinished prompt")
        app._last_input_buffer = "Previously cleared prompt"
        app._pending_tool_calls = {"c1": {
            "call_id": "c1", "name": "read", "arguments": "{}", "needs_approval": True,
        }}
        app._show_tool_approval_modal()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ToolApprovalScreen)
        feedback = screen.query_one("#feedback-input", Input)
        feedback.focus()
        mode = app._agent_mode
        await pilot.press("shift+tab")
        assert app.focused is screen.query_one("#reject-c1")
        assert app._agent_mode == mode
        await pilot.press("tab")
        assert app.focused is feedback
        feedback.value = "review this"
        feedback.cursor_position = len(feedback.value)
        await pilot.press("ctrl+a")
        assert feedback.cursor_position == 0
        await pilot.press("ctrl+d")
        assert feedback.value == "eview this"
        assert app.screen is screen
        feedback.cursor_position = 5
        await pilot.press("ctrl+u")
        assert feedback.value == " this"
        await pilot.press("ctrl+y")
        assert app.focused is feedback
        assert composer.text == "Unfinished prompt"
        assert app._last_input_buffer == "Previously cleared prompt"
        feedback.value = "copy me"
        await pilot.press("ctrl+shift+a", "ctrl+c")
        assert app.clipboard == "copy me"
        assert app.screen is screen
        assert screen._decisions == {}
        assert results == []
        await pilot.press("escape")
        assert results == [ToolApprovalResult(decisions={"c1": "deny"}, feedback="copy me")]
        assert app.focused is composer
        assert composer.text == "Unfinished prompt"
        fake_client.send_decision.assert_not_called()


@pytest.mark.asyncio
async def test_main_composer_shortcuts_remain_available(fake_client: AsyncMock) -> None:
    app = AgentApp(client=fake_client)
    async with app.run_test() as pilot:
        composer = app.screen.query_one(InputTextArea)
        composer.load_text("Main prompt")
        await pilot.press("ctrl+a")
        assert composer.selected_text == "Main prompt"
        await pilot.press("ctrl+u")
        assert composer.text == ""
        await pilot.press("ctrl+y")
        assert composer.text == "Main prompt"
        mode = app._agent_mode
        await pilot.press("shift+tab")
        assert app._agent_mode != mode
        composer.move_cursor((0, len(composer.text)))
        await pilot.press("ctrl+c")
        assert isinstance(app.screen, ExitConfirmScreen)
        await pilot.press("n", "ctrl+d")
        assert isinstance(app.screen, ExitConfirmScreen)
        await pilot.press("n")
        assert app.focused is composer
