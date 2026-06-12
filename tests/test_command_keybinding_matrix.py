"""Coverage matrix for every slash command and key binding.

Complements the per-command unit tests by asserting, in one place, that the whole
registry is dispatchable and every declared key binding maps to a real action that
runs without raising on a live (mounted) app driven through the Pilot harness.
"""

import pytest

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.screens.main import MainScreen


def _command_names() -> list[str]:
    # The registry is built in CommandProcessor.__init__; read it off a throwaway.
    from agent_terminal_ui.commands import CommandProcessor

    return sorted(CommandProcessor(object()).commands)


def _binding_keys(bindings) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for b in bindings:
        # Binding.key may be comma-joined (e.g. "escape,escape"); take the first.
        key = b.key.split(",")[0]
        out.append((key, b.action))
    return out


@pytest.mark.parametrize("name", _command_names())
async def test_every_command_is_dispatchable(app: AgentApp, name: str) -> None:
    """Each registered slash command is recognized and runs without raising."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # Bare invocation (no args) must hit a usage/handler path, never crash.
        handled = await app._cmd_processor.process(f"/{name}")
        await pilot.pause()
        assert handled is True


async def test_unknown_command_is_reported(app: AgentApp) -> None:
    async with app.run_test(size=(120, 40)):
        handled = await app._cmd_processor.process("/definitely-not-a-command")
        assert handled is True  # consumed (reported as unknown), not forwarded


@pytest.mark.parametrize(
    "key,action",
    _binding_keys(AgentApp.BINDINGS) + _binding_keys(MainScreen.BINDINGS),
)
async def test_every_binding_action_exists_and_runs(
    app: AgentApp, key: str, action: str
) -> None:
    """Every bound key resolves to an existing action that runs without raising."""
    holder = app if hasattr(app, f"action_{action}") else None
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        target = holder or app.screen
        assert hasattr(target, f"action_{action}"), (
            f"binding {key!r} -> action_{action} has no handler"
        )
        await pilot.press(key)
        await pilot.pause()


@pytest.mark.parametrize(
    "keys,expected_mode",
    [
        (["/", "p", "l", "a", "n", "enter"], "plan"),
        (["/", "b", "u", "i", "l", "d", "enter"], "code"),
    ],
)
async def test_slash_mode_switch_via_keyboard(
    app: AgentApp, keys: list[str], expected_mode: str
) -> None:
    """Typing a mode slash command through the input widget switches mode."""
    from agent_terminal_ui.tui.input_text_area import InputTextArea

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.click(InputTextArea)
        await pilot.press(*keys)
        await pilot.pause()
        assert app._agent_mode == expected_mode


def test_agents_mode_registered() -> None:
    """The Agent View screen mode is wired so /agents has somewhere to go."""
    assert "main" in AgentApp.MODES and "agents" in AgentApp.MODES
