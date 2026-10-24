"""Canopy extends the existing Textual palette and mounted controls."""

from unittest.mock import AsyncMock

import pytest
from textual.color import Color

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.themes import CANOPY
from agent_terminal_ui.tui.input_text_area import InputTextArea

pytestmark = pytest.mark.spec("TUI-RUNTIME-R008.3", "TUI-RUNTIME-R008.3.1")


def luminance(value: str) -> float:
    color = Color.parse(value)
    channels = [channel / 255 for channel in (color.r, color.g, color.b)]
    linear = [
        v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels
    ]
    return sum(
        v * weight for v, weight in zip(linear, [0.2126, 0.7152, 0.0722], strict=True)
    )


def test_canopy_text_and_selection_tokens_have_readable_opaque_contrast() -> None:
    tokens = CANOPY.to_color_system().generate()
    pairs = [
        (text, surface)
        for text in (
            "foreground",
            "text-muted",
            "foreground-muted",
            "primary",
            "secondary",
            "accent",
            "warning",
            "error",
            "success",
        )
        for surface in ("background", "surface", "panel")
    ]
    pairs.extend(
        [
            ("input-selection-foreground", "input-selection-background"),
            ("block-cursor-foreground", "block-cursor-background"),
            ("button-color-foreground", "primary"),
        ]
    )
    for foreground, background in pairs:
        a, b = (luminance(tokens[name]) for name in (foreground, background))
        assert (max(a, b) + 0.05) / (min(a, b) + 0.05) >= 4.5, (foreground, background)
        assert Color.parse(tokens[foreground]).a == 1.0
        assert Color.parse(tokens[background]).a == 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "term,no_color", [("xterm-256color", None), ("dumb", ""), ("xterm-256color", "1")]
)
async def test_canopy_mounted_selection_resize_and_cycle_preserve_input(
    fake_client: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    term: str,
    no_color: str | None,
) -> None:
    monkeypatch.setenv("TERM", term)
    if no_color is None:
        monkeypatch.delenv("NO_COLOR", raising=False)
    else:
        monkeypatch.setenv("NO_COLOR", no_color)
    app = AgentApp(theme_name="canopy", client=fake_client)
    async with app.run_test(size=(100, 30)) as pilot:
        composer = app.screen.query_one(InputTextArea)
        composer.load_text("Keep this draft while changing the view")
        for width, height in [(40, 16), (120, 32), (80, 24)]:
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            assert app.theme == "canopy"
            assert app.focused is composer
            assert composer.text == "Keep this draft while changing the view"
            assert app.no_color is (no_color is not None)
        themes = list(app.available_themes)
        assert all(
            name in themes
            for name in ("tokyo-night", "nord", "gruvbox", "textual-light")
        )
        for _ in themes:
            await pilot.press("alt+shift+t")
        assert app.theme == "canopy"
        assert composer.text == "Keep this draft while changing the view"
        assert app.focused is composer
