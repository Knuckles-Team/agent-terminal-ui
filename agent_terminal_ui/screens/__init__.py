"""Screen modules for the Agent Terminal UI.

Provides the screen-based architecture following Textual best practices:
- MainScreen: Primary chat/conversation interface
- PermissionsScreen: Tool approval with danger indicators and diff views
- SettingsScreen: In-app settings editor with schema-driven forms

Concept: AU-018 (TUI Screen Architecture)
"""

from agent_terminal_ui.screens.main import MainScreen
from agent_terminal_ui.screens.permissions import PermissionsScreen
from agent_terminal_ui.screens.settings import SettingsScreen

__all__ = ["MainScreen", "PermissionsScreen", "SettingsScreen"]
