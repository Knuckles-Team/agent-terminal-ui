"""Stylesheets referenced by production screens must be package resources."""

from importlib.resources import files

import pytest

from agent_terminal_ui.screens.main import MainScreen
from agent_terminal_ui.screens.permissions import PermissionsScreen


@pytest.mark.spec("TUI-RUNTIME-R001.7")
@pytest.mark.parametrize("screen", [MainScreen, PermissionsScreen])
def test_screen_stylesheet_is_packaged(screen):
    package = screen.__module__.rsplit(".", 1)[0]
    assert files(package).joinpath(screen.CSS_PATH).read_text().strip()
