"""Settings screen for the Agent Terminal UI.

Provides an in-app settings editor with schema-driven form generation,
search filtering, and auto-persist.

Concept: AU-018 (Settings Screen)
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalGroup, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Footer, Input, Select, Static

from agent_terminal_ui.settings import SETTINGS_SCHEMA, AppSettings


class SettingsScreen(ModalScreen):
    """In-app settings editor modal.

    Generates form fields from the settings schema and applies
    changes in real-time with auto-save.
    """

    BINDINGS = [
        ("escape", "dismiss", "Close settings"),
    ]

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
        background: $background 80%;
    }

    #settings-container {
        width: 70%;
        max-width: 80;
        height: 80%;
        background: $surface;
        border: solid $primary;
        padding: 2;
    }

    #settings-title {
        height: 1;
        text-style: bold;
        text-align: center;
        color: $primary;
        margin: 0 0 1 0;
    }

    #settings-search {
        margin: 0 0 1 0;
    }

    #settings-list {
        height: 1fr;
    }

    .setting-group {
        height: auto;
        margin: 0 0 1 0;
        padding: 1;
        border: solid $primary 20%;
    }

    .setting-title {
        text-style: bold;
        margin: 0 0 0 0;
    }

    .setting-help {
        color: $text-muted;
        margin: 0 0 1 0;
    }

    .setting-input {
        margin: 0;
    }
    """

    def __init__(
        self,
        settings: AppSettings,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the settings screen.

        Args:
            settings: The AppSettings instance.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._settings = settings

    def compose(self) -> ComposeResult:
        """Compose the settings screen layout."""
        with Vertical(id="settings-container"):
            yield Static("⚙ Settings", id="settings-title", markup=True)
            yield Input(
                id="settings-search",
                placeholder="Search settings...",
            )

            with VerticalScroll(id="settings-list"):
                for setting_def in SETTINGS_SCHEMA:
                    if not setting_def.editable:
                        continue

                    with VerticalGroup(
                        classes="setting-group",
                        name=setting_def.title.lower(),
                    ):
                        yield Static(
                            setting_def.title,
                            classes="setting-title",
                        )
                        if setting_def.help:
                            yield Static(
                                f"[dim]{setting_def.help}[/dim]",
                                classes="setting-help",
                                markup=True,
                            )

                        value = self._settings.get(setting_def.key, expand=False)

                        if setting_def.type == "string":
                            yield Input(
                                str(value or ""),
                                classes="setting-input",
                                name=setting_def.key,
                            )
                        elif setting_def.type == "boolean":
                            yield Checkbox(
                                value=bool(value),
                                classes="setting-input",
                                name=setting_def.key,
                            )
                        elif setting_def.type == "choices":
                            choices = [(c, c) for c in (setting_def.choices or [])]
                            yield Select(
                                choices,
                                value=str(value),
                                classes="setting-input",
                                name=setting_def.key,
                                allow_blank=False,
                            )
                        elif setting_def.type == "integer":
                            yield Input(
                                str(value or 0),
                                type="integer",
                                classes="setting-input",
                                name=setting_def.key,
                            )

        yield Footer()

    @on(Input.Changed, "#settings-search")
    def _on_search(self, event: Input.Changed) -> None:
        """Filter settings by search query."""
        query = event.value.lower()
        for group in self.query(".setting-group"):
            if group.name:
                group.display = not query or query in group.name

    @on(Input.Blurred, ".setting-input")
    def _on_input_blurred(self, event: Input.Blurred) -> None:
        """Save input setting on blur."""
        if event.input.name:
            self._settings.set(event.input.name, event.value)

    @on(Checkbox.Changed, ".setting-input")
    def _on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Save checkbox setting on change."""
        if event.checkbox.name:
            self._settings.set(event.checkbox.name, event.checkbox.value)

    @on(Select.Changed, ".setting-input")
    def _on_select_changed(self, event: Select.Changed) -> None:
        """Save select setting on change."""
        if event.select.name:
            self._settings.set(event.select.name, event.select.value)
            # Apply theme changes immediately
            if event.select.name == "theme":
                self.app.theme = str(event.select.value)
