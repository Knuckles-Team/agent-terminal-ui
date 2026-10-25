from unittest.mock import MagicMock

import pytest

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.settings import SETTINGS_SCHEMA, AppSettings
from agent_terminal_ui.tui.input_text_area import InputTextArea
from agent_terminal_ui.tui.status_line import StatusLine


@pytest.mark.asyncio
async def test_requests_have_no_mode_control(fake_client):
    app = AgentApp(client=fake_client)
    async with app.run_test() as pilot:
        assert not hasattr(app, "_agent_mode")
        assert not app.query_one(StatusLine).query("#status-mode")
        assert not {"plan", "chat", "build"} & app._cmd_processor.commands.keys()
        composer = app.query_one(InputTextArea)
        composer.load_text("Please make a plan")
        await pilot.press("shift+tab")
        assert composer.text == "Please make a plan"
        assert not hasattr(app, "_agent_mode")


def test_request_mode_is_not_a_setting():
    assert "default_mode" not in {setting.key for setting in SETTINGS_SCHEMA}


@pytest.mark.asyncio
async def test_stale_request_mode_preference_cannot_control_submission(
    fake_client, tmp_path, monkeypatch
):
    settings_file = tmp_path / "settings.toml"
    settings_file.write_text('default_mode = "build"\n')
    monkeypatch.setenv("DEFAULT_MODE", "plan")
    settings = AppSettings(settings_file)
    assert "default_mode" not in settings.schema
    app = AgentApp(client=fake_client)
    async with app.run_test():
        app._run_agent_turn = MagicMock()
        await app._submit_prompt("Please explain this change")
        app._run_agent_turn.assert_called_once_with(
            "Please explain this change", parts=[], model=None
        )
        assert not hasattr(app, "_agent_mode")
    assert settings_file.read_text() == 'default_mode = "build"\n'
