"""Screen modules for the Agent Terminal UI.

Provides the screen-based architecture following Textual best practices:
- MainScreen: Primary chat/conversation interface
- PermissionsScreen: Tool approval with danger indicators and diff views
- SettingsScreen: In-app settings editor with schema-driven forms
- DashboardScreen: Service dashboard with live-updating widget cards

Concept: AU-018 (TUI Screen Architecture)
"""

from agent_terminal_ui.screens.main import MainScreen
from agent_terminal_ui.screens.permissions import PermissionsScreen
from agent_terminal_ui.screens.settings import SettingsScreen

# Lazy import to avoid hard dependency on service-dashboard-core
try:
    from agent_terminal_ui.screens.dashboard import DashboardScreen
except ImportError:
    DashboardScreen = None  # type: ignore[assignment,misc]

__all__ = ["MainScreen", "PermissionsScreen", "SettingsScreen", "DashboardScreen"]
