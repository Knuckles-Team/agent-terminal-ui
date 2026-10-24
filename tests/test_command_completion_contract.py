"""Mounted command completion preserves exact names and resolves aliases."""

import pytest
from textual.app import App, ComposeResult

from agent_terminal_ui.commands import CommandProcessor
from agent_terminal_ui.tui.input_text_area import CommandSuggestionsOverlay, InputTextArea

pytestmark = pytest.mark.spec("TUI-RUNTIME-R012.4.3.1")


class CompletionApp(App):
    def __init__(self) -> None:
        super().__init__()
        self._cmd_processor = CommandProcessor(self)
        self.submitted: list[str] = []

    def compose(self) -> ComposeResult:
        yield InputTextArea(commands=self._cmd_processor.commands)

    def on_input_text_area_submitted(self, event: InputTextArea.Submitted) -> None:
        self.submitted.append(event.value)


@pytest.mark.asyncio
@pytest.mark.parametrize('command', ['/mcp', '/queue', '/run', '/MCP', '/runs'])
async def test_tab_preserves_exact_command_instead_of_longer_sibling(command: str) -> None:
    app = CompletionApp()
    async with app.run_test() as pilot:
        area = app.query_one(InputTextArea)
        area.load_text(command)
        area.focus()
        await pilot.press('tab')
        await pilot.pause()
        assert area.text == command + ' '
        assert not app.submitted
        await pilot.press('enter')
        await pilot.pause()
        assert app.submitted == [command + ' ']


@pytest.mark.asyncio
@pytest.mark.parametrize('key', ['enter', 'tab'])
@pytest.mark.parametrize(('prefix', 'expected'), [('/FOC', '/focus '), ('/ru', '/run '), ('/QUI', '/exit ')])
async def test_unique_completion_matches_dispatch_case_and_canonical_aliases(key: str, prefix: str, expected: str) -> None:
    app = CompletionApp()
    async with app.run_test() as pilot:
        area = app.query_one(InputTextArea)
        area.load_text(prefix)
        area.focus()
        await pilot.press(key)
        await pilot.pause()
        assert area.text == expected
        assert not app.submitted


@pytest.mark.asyncio
@pytest.mark.parametrize('text', ['/q', '/mcp reload', '/run\tplan task'])
async def test_ambiguous_prefixes_and_arguments_are_not_replaced(text: str) -> None:
    app = CompletionApp()
    async with app.run_test() as pilot:
        area = app.query_one(InputTextArea)
        area.load_text(text)
        area.focus()
        await pilot.press('enter')
        await pilot.pause()
        assert app.submitted == [text]
        assert area.text == text


@pytest.mark.asyncio
@pytest.mark.parametrize(('query', 'expected'), [('QUI', ['exit']), ('ru', ['run']), ('MCP', ['mcp', 'mcp:reload'])])
async def test_suggestion_filter_matches_aliases_without_duplicate_rows(query: str, expected: list[str]) -> None:
    app = CompletionApp()
    async with app.run_test() as pilot:
        processor = app._cmd_processor
        overlay = CommandSuggestionsOverlay(processor.commands, lambda name: None, lambda: None, canonical_commands=processor.canonical_commands)
        await app.mount(overlay)
        await pilot.pause()
        overlay.filter_commands(query)
        await pilot.pause()
        assert overlay._filtered_commands == expected
