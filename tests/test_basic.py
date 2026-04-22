import pytest


def test_basic_import():
    import agent_terminal_ui

    assert agent_terminal_ui is not None


@pytest.mark.asyncio
async def test_terminal_ui_app_imports():
    from agent_terminal_ui.app import AgentApp

    app = AgentApp()
    assert app.CSS is not None
