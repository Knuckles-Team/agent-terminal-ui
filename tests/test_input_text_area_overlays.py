"""Fifth-pass coverage uplift focused on ``input_text_area.py`` internals.

Drives the overlays through their enter/tab/escape key handlers to cover
``on_list_view_selected``, ``filter_*``, ``_show_*_popup``, and
``_close_*_overlay`` branches.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from textual.app import App, ComposeResult

from agent_terminal_ui.tui.input_text_area import (
    CommandSuggestionsOverlay,
    FileSuggestionsOverlay,
    InputTextArea,
)


@pytest.mark.asyncio
async def test_command_overlay_docstring_variants():
    """Exercise the description-extraction branches (dict / callable / usage)."""

    class _Dummy:
        """Dict-shaped command handler with Usage: prefix.

        Usage: /dummy something
        """

        __slots__ = ()

    async def call_doc(args):
        """A callable command. Usage: /call"""
        return None

    dict_cmd = {"description": "dict description"}

    class _Host(App):
        def compose(self) -> ComposeResult:
            self._overlay = CommandSuggestionsOverlay(
                {
                    "call": call_doc,
                    "dict_cmd": dict_cmd,
                },
                on_select=lambda c: None,
                on_close=lambda: None,
            )
            yield self._overlay

    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()


@pytest.mark.asyncio
async def test_command_overlay_on_list_view_selected_dispatches():
    selected: list[str] = []

    class _Host(App):
        def compose(self) -> ComposeResult:
            self._overlay = CommandSuggestionsOverlay(
                {"help": lambda a: None, "quit": lambda a: None},
                on_select=selected.append,
                on_close=lambda: None,
                canonical_commands={"quit": "exit"},
            )
            yield self._overlay

    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        overlay = app._overlay
        # Force-set filtered commands and trigger list selection
        overlay._filtered_commands = ["quit"]
        from textual.widgets import ListView

        lv = overlay.query_one("#suggestions-list", ListView)
        lv.index = 0
        # Construct a fake Selected event via SimpleNamespace
        fake_item = SimpleNamespace()
        fake_evt = SimpleNamespace(item=fake_item, list_view=lv)
        overlay.on_list_view_selected(fake_evt)
    assert selected == ["exit"]


@pytest.mark.asyncio
async def test_file_overlay_on_list_view_selected_dispatches(tmp_path, monkeypatch):
    (tmp_path / "foo.py").write_text("")
    monkeypatch.chdir(tmp_path)
    selected: list[str] = []

    class _Host(App):
        def compose(self) -> ComposeResult:
            self._overlay = FileSuggestionsOverlay(
                on_select=selected.append,
                on_close=lambda: None,
                initial_query="foo",
            )
            yield self._overlay

    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        overlay = app._overlay
        overlay._filtered_files = ["foo.py"]
        from textual.widgets import ListView

        lv = overlay.query_one("#file-suggestions-list", ListView)
        lv.index = 0
        evt = SimpleNamespace(item=SimpleNamespace(), list_view=lv)
        overlay.on_list_view_selected(evt)
    assert selected == ["foo.py"]


@pytest.mark.asyncio
async def test_input_text_area_show_file_popup_triggers_overlay(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("")
    monkeypatch.chdir(tmp_path)

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield InputTextArea(commands={})

    app = _Host()
    async with app.run_test() as pilot:
        area = app.query_one(InputTextArea)
        area.text = "talk @a"
        area._show_file_popup()
        await pilot.pause()
        assert area._file_overlay is not None
        # Calling again does not re-mount
        area._show_file_popup()
        area._close_file_overlay()
        assert area._file_overlay is None


@pytest.mark.asyncio
async def test_input_text_area_show_suggestion_popup_triggers_overlay():
    async def help_cmd(args):
        """Help command."""
        return None

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield InputTextArea(commands={"help": help_cmd})

    app = _Host()
    async with app.run_test() as pilot:
        area = app.query_one(InputTextArea)
        area.text = "/he"
        area._show_suggestion_popup()
        await pilot.pause()
        assert area._suggestion_overlay is not None
        # No-op on second call
        area._show_suggestion_popup()
        area._close_suggestion_overlay()
        assert area._suggestion_overlay is None


@pytest.mark.asyncio
async def test_input_text_area_show_suggestion_popup_no_commands():
    class _Host(App):
        def compose(self) -> ComposeResult:
            yield InputTextArea(commands={})

    app = _Host()
    async with app.run_test():
        area = app.query_one(InputTextArea)
        area.text = "/unknown"
        area._show_suggestion_popup()
        assert area._suggestion_overlay is None


@pytest.mark.asyncio
async def test_input_text_area_show_suggestion_popup_not_slash():
    async def help_cmd(args):
        """Help."""
        return None

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield InputTextArea(commands={"help": help_cmd})

    app = _Host()
    async with app.run_test():
        area = app.query_one(InputTextArea)
        area.text = "no slash"
        area._show_suggestion_popup()
        assert area._suggestion_overlay is None


@pytest.mark.asyncio
async def test_input_text_area_show_command_suggestions_autocomplete_single():
    async def helpme(args):
        """Helpme."""
        return None

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield InputTextArea(commands={"helpme": helpme})

    app = _Host()
    async with app.run_test() as pilot:
        area = app.query_one(InputTextArea)
        area.text = "/h"
        area._show_command_suggestions()
        await pilot.pause()
        assert area.text.startswith("/helpme")


@pytest.mark.asyncio
async def test_input_text_area_show_command_suggestions_no_matches():
    async def foo(args):
        """foo."""
        return None

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield InputTextArea(commands={"foo": foo})

    app = _Host()
    async with app.run_test():
        area = app.query_one(InputTextArea)
        area.text = "/nope"
        area._show_command_suggestions()  # no matches → no-op


@pytest.mark.asyncio
async def test_input_text_area_show_command_suggestions_not_slash():
    class _Host(App):
        def compose(self) -> ComposeResult:
            yield InputTextArea(commands={})

    app = _Host()
    async with app.run_test():
        area = app.query_one(InputTextArea)
        area.text = "notaslash"
        area._show_command_suggestions()
        area._show_file_suggestions()


@pytest.mark.asyncio
async def test_input_text_area_show_file_suggestions_no_at():
    class _Host(App):
        def compose(self) -> ComposeResult:
            yield InputTextArea(commands={})

    app = _Host()
    async with app.run_test():
        area = app.query_one(InputTextArea)
        area.text = "no at here"
        area._show_file_suggestions()  # early return
        area._show_file_popup()  # early return when no @


@pytest.mark.asyncio
async def test_input_text_area_update_suggestion_popup():
    async def cmd(args):
        """A cmd."""
        return None

    class _Host(App):
        def compose(self) -> ComposeResult:
            yield InputTextArea(commands={"cmd": cmd})

    app = _Host()
    async with app.run_test():
        area = app.query_one(InputTextArea)
        area.text = "/c"
        area._update_suggestion_popup()  # delegates to _show_suggestion_popup
