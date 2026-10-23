"""Whole-application keyboard access to public run folds."""

from unittest.mock import AsyncMock

import pytest

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.tui.input_text_area import InputTextArea
from agent_terminal_ui.widgets.conversation import Conversation
from agent_terminal_ui.widgets.public_run_details import PublicRunDetails
from tests.test_public_run_details import binding, page

pytestmark = pytest.mark.spec("TUI-RUNTIME-R008.2.3.2.2.2.1")


@pytest.mark.asyncio
async def test_composer_keyboard_route_preserves_fold_state(
    fake_client: AsyncMock,
) -> None:
    fake_client.get_public_run_events.return_value = page()
    app = AgentApp(client=fake_client)
    async with app.run_test(size=(120, 35)) as pilot:
        conversation = app.screen.query_one(Conversation)
        await conversation.add_user_message("Compare options\n" * 60)
        await conversation.bind_public_run(fake_client, binding())
        details = app.screen.query_one(PublicRunDetails)
        composer = app.screen.query_one(InputTextArea)
        assert app.focused is composer
        await pilot.press("f8")
        assert app.focused is conversation
        await pilot.press("tab")
        assert app.focused is details.summary_fold.query_one("CollapsibleTitle")
        await pilot.press("enter")
        await pilot.pause()
        assert not details.summary_fold.collapsed
        await pilot.press("tab", "space")
        await pilot.pause()
        title = details.trace_fold.query_one("CollapsibleTitle")
        assert app.focused is title
        assert not details.trace_fold.collapsed
        previous_scroll = conversation.scroll_y
        await pilot.press("pageup")
        await pilot.pause()
        retained_scroll = conversation.scroll_y
        assert retained_scroll < previous_scroll
        before = [record.event_id for record in details.records]
        assert before
        await pilot.press("r")
        await pilot.pause()
        assert app.focused is title
        assert conversation.scroll_y == retained_scroll
        assert [record.event_id for record in details.records] == before
        assert not details.summary_fold.collapsed and not details.trace_fold.collapsed
        await pilot.press("f8")
        assert app.focused is composer
        assert composer.text == ""
        await pilot.press("ctrl+q")
