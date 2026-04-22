#!/usr/bin/python
"""Input text area component for user queries.

Customization of the Textual TextArea to handle submission on Enter and
properly manage multi-line input via Shift+Enter (or backslash-escaped Enter
on some terminals).
"""

import logging

from textual import events
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ListItem, ListView, Static, TextArea

logger = logging.getLogger(__name__)


class CommandSuggestionsOverlay(Widget):
    """A non-modal overlay showing command suggestions."""

    DEFAULT_CSS = """
    CommandSuggestionsOverlay {
        layer: command_suggestions;
        dock: top;
        height: auto;
        max-height: 40%;
        padding: 1;
        background: $surface;
        border: solid $border;
    }

    #suggestions-title {
        text-align: center;
        text-style: bold;
        padding: 0 0 1 0;
        color: $primary;
    }

    #suggestions-list {
        height: auto;
    }

    ListItem {
        padding: 0 1;
    }

    ListItem.-selected {
        background: $primary;
    }
    """

    def __init__(
        self,
        commands: dict,
        on_select,
        on_close,
        initial_query: str = "",
        canonical_commands=None,
    ):
        """Initialize the suggestions overlay.

        Args:
            commands: Dictionary of available commands
            on_select: Callback when a command is selected
            on_close: Callback when the overlay is closed
            initial_query: Initial query to filter commands
            canonical_commands: Dictionary mapping aliases to canonical command names
        """
        super().__init__()
        self._commands = commands
        self._canonical_commands = canonical_commands or {}
        self._on_select = on_select
        self._on_close = on_close
        self._filtered_commands = list(commands.keys())
        self._initial_query = initial_query
        self._selected_index = 0

    def compose(self):
        """Compose the overlay UI."""
        yield Static(
            "Available Commands (ESC to close, TAB to cycle)",
            id="suggestions-title",
        )
        yield ListView(id="suggestions-list")

    def on_mount(self):
        """Set up the overlay when mounted."""
        if self._initial_query:
            self.filter_commands(self._initial_query)
        else:
            self._update_list()

    def filter_commands(self, query: str):
        """Filter commands based on query.

        Args:
            query: The current input after the slash
        """
        if not query:
            self._filtered_commands = sorted(self._commands.keys())
        else:
            self._filtered_commands = sorted(
                [cmd for cmd in self._commands.keys() if cmd.startswith(query)]
            )
        self._update_list()

    def _update_list(self):
        """Update the list view with filtered commands."""
        list_view = self.query_one("#suggestions-list", ListView)
        list_view.clear()

        for cmd in self._filtered_commands:
            # Get the canonical command name (for aliases)
            display_cmd = self._canonical_commands.get(cmd, cmd)

            # Get command description if available
            description = ""
            if callable(self._commands.get(cmd)):
                description = self._commands[cmd].__doc__ or ""
            elif isinstance(self._commands.get(cmd), dict):
                description = self._commands[cmd].get("description", "")

            # Clean up description: remove line breaks and "Usage:" parts
            description = description.replace("\n", " ").replace("\r", " ")
            # Remove "Usage:" prefix if present
            if "Usage:" in description:
                description = description.split("Usage:")[0].strip()
            # Remove trailing periods and extra whitespace
            description = description.rstrip(".").strip()
            # Truncate to reasonable length
            description = description[:60]

            item = ListItem(
                Static(
                    f"[bold cyan]/{display_cmd}[/bold cyan] [dim]{description}[/dim]"
                )
            )
            list_view.append(item)

        if self._filtered_commands:
            list_view.index = 0

    def on_list_view_selected(self, event: ListView.Selected):
        """Handle when a list item is selected."""
        if event.item:
            if event.list_view.index is not None and event.list_view.index < len(
                self._filtered_commands
            ):
                command = self._filtered_commands[event.list_view.index]
                # Get the canonical command name (for aliases)
                canonical_command = self._canonical_commands.get(command, command)
                self._on_select(canonical_command)

    def on_key(self, event: events.Key):
        """Handle key events in the overlay."""
        if event.key == "escape":
            self._on_close()
            event.stop()
            event.prevent_default()
        elif event.key == "tab":
            # Tab cycles through suggestions
            list_view = self.query_one("#suggestions-list", ListView)
            if list_view.index is not None:
                list_view.index = (list_view.index + 1) % len(list_view.children)
            event.stop()
            event.prevent_default()
        elif event.key == "enter":
            # Select the current item
            list_view = self.query_one("#suggestions-list", ListView)
            if list_view.index is not None and list_view.index < len(
                self._filtered_commands
            ):
                command = self._filtered_commands[list_view.index]
                # Get the canonical command name (for aliases)
                canonical_command = self._canonical_commands.get(command, command)
                self._on_select(canonical_command)
            event.stop()
            event.prevent_default()


class FileSuggestionsOverlay(Widget):
    """A non-modal overlay showing file suggestions."""

    DEFAULT_CSS = """
    FileSuggestionsOverlay {
        layer: file_suggestions;
        dock: top;
        height: auto;
        max-height: 40%;
        padding: 1;
        background: $surface;
        border: solid $border;
    }

    #file-suggestions-title {
        text-align: center;
        text-style: bold;
        padding: 0 0 1 0;
        color: $secondary;
    }

    #file-suggestions-list {
        height: auto;
    }

    ListItem {
        padding: 0 1;
    }

    ListItem.-selected {
        background: $secondary;
    }
    """

    def __init__(self, on_select, on_close, initial_query: str = ""):
        """Initialize the file suggestions overlay.

        Args:
            on_select: Callback when a file is selected
            on_close: Callback when the overlay is closed
            initial_query: Initial query to filter files
        """
        super().__init__()
        self._on_select = on_select
        self._on_close = on_close
        self._all_files: list[str] = []
        self._filtered_files: list[str] = []
        self._initial_query = initial_query
        self._load_files()

    def _load_files(self):
        """Load files from the current workspace."""
        import os

        # Simple heuristic: list files in current dir, excluding hidden ones
        files = []
        try:
            for root, dirs, filenames in os.walk("."):
                # Exclude common noisy directories
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".")
                    and d not in ("node_modules", "__pycache__", "venv")
                ]
                for f in filenames:
                    rel_path = os.path.relpath(os.path.join(root, f), ".")
                    if not rel_path.startswith("."):
                        files.append(rel_path)
                    if len(files) > 1000:  # Limit for performance
                        break
                if len(files) > 1000:
                    break
        except Exception:
            pass
        self._all_files = sorted(files)
        self._filtered_files = self._all_files

    def compose(self):
        """Compose the overlay UI."""
        yield Static(
            "File Mentions (ESC to close, TAB to cycle)",
            id="file-suggestions-title",
        )
        yield ListView(id="file-suggestions-list")

    def on_mount(self):
        """Set up the overlay when mounted."""
        if self._initial_query:
            self.filter_files(self._initial_query)
        else:
            self._update_list()

    def filter_files(self, query: str):
        """Filter files based on query.

        Args:
            query: The current input after the @
        """
        if not query:
            self._filtered_files = self._all_files[:100]  # Limit display
        else:
            query_lower = query.lower()
            self._filtered_files = [
                f for f in self._all_files if query_lower in f.lower()
            ][:100]
        self._update_list()

    def _update_list(self):
        """Update the list view with filtered files."""
        list_view = self.query_one("#file-suggestions-list", ListView)
        list_view.clear()

        for f in self._filtered_files:
            item = ListItem(Static(f"[bold cyan]@{f}[/bold cyan]"))
            list_view.append(item)

        if self._filtered_files:
            list_view.index = 0

    def on_list_view_selected(self, event: ListView.Selected):
        """Handle when a list item is selected."""
        if event.item and event.list_view.index is not None:
            if event.list_view.index < len(self._filtered_files):
                filename = self._filtered_files[event.list_view.index]
                self._on_select(filename)

    def on_key(self, event: events.Key):
        """Handle key events in the overlay."""
        if event.key == "escape":
            self._on_close()
            event.stop()
            event.prevent_default()
        elif event.key == "tab":
            list_view = self.query_one("#file-suggestions-list", ListView)
            if list_view.index is not None:
                list_view.index = (list_view.index + 1) % len(list_view.children)
            event.stop()
            event.prevent_default()
        elif event.key == "enter":
            list_view = self.query_one("#file-suggestions-list", ListView)
            if list_view.index is not None and list_view.index < len(
                self._filtered_files
            ):
                filename = self._filtered_files[list_view.index]
                self._on_select(filename)
            event.stop()
            event.prevent_default()


class InputTextArea(TextArea):
    """Custom TextArea optimized for interactive chat input.

    Interprets the 'Enter' key as a submission event while allowing
    multi-line input through various terminal-specific escape sequences.
    """

    class Submitted(Message):
        """Posted when the user intends to submit their input to the agent.

        Attributes:
            value: The full text content of the area at the time of submission.

        """

        def __init__(self, value: str) -> None:
            """Initialize the submission message.

            Args:
                value: The content string to be submitted.

            """
            self.value = value
            super().__init__()

    def __init__(self, *args, commands: dict | None = None, **kwargs) -> None:
        """Initialize the input text area.

        Args:
            *args: Positional arguments passed to the base TextArea.
            commands: Dictionary of available slash commands for suggestions.
            **kwargs: Keyword arguments passed to the base TextArea.

        """
        super().__init__(*args, **kwargs)
        self._last_key_was_backslash: bool = False
        self._commands: dict = commands or {}
        self._show_suggestions = False
        self._suggestion_overlay: CommandSuggestionsOverlay | None = None
        self._file_overlay: FileSuggestionsOverlay | None = None

    def on_key(self, event: events.Key) -> None:
        """Handle key events to intercept submission and control newlines.

        Supports a specific heuristic for Shift+Enter emulation:
        - Backslash followed by Enter results in a newline.
        - Plain Enter results in a 'Submitted' message.

        Args:
            event: The Textual key event to process.

        """
        # Tab key triggers suggestions (commands or files)
        if event.key == "tab":
            current_text: str = self.text.strip()  # type: ignore[has-type]
            if "@" in current_text:
                self._show_file_suggestions()
            else:
                self._show_command_suggestions()
            event.stop()
            event.prevent_default()
            return

        # Escape key closes overlays
        if event.key == "escape":
            self._close_suggestion_overlay()
            self._close_file_overlay()
            event.stop()
            event.prevent_default()
            return

        # Some terminals send backslash followed by enter as two separate events for
        # Shift+Enter (instead of a single "shift+enter" key). We detect this pattern
        # by tracking when backslash is pressed and checking if enter follows.
        if event.key == "backslash":
            self._last_key_was_backslash = True
            event.stop()
            event.prevent_default()
            return

        if event.key == "enter":
            event.stop()
            event.prevent_default()
            if self._last_key_was_backslash:
                self._last_key_was_backslash = False
                self.insert("\n")
            else:
                # Check if there are matching commands for autocomplete
                current_text_enter: str = self.text.strip()  # type: ignore[has-type]
                if current_text_enter.startswith("/") and not self._suggestion_overlay:
                    # Find matching commands
                    matches = [
                        cmd
                        for cmd in self._commands.keys()
                        if cmd.startswith(current_text_enter[1:]) and cmd != current_text_enter[1:]
                    ]
                    if matches:
                        # Autocomplete to the first match
                        self.text = f"/{matches[0]} "
                        self.cursor_position = len(self.text)
                        return
                # Submit the input
                self.post_message(self.Submitted(self.text))
            return

        if self._last_key_was_backslash:
            # Handle cases where the user actually intended to type a literal backslash.
            # If any other key follows the backslash, we insert the backslash first.
            self.insert("\\")
            self._last_key_was_backslash = False

        # Detect "@" character to show file suggestions immediately
        if event.character == "@":
            # Show suggestions after the @ is inserted
            def show_if_at_still_there():
                if "@" in self.text:
                    self._show_file_popup()

            self.set_timer(0.01, show_if_at_still_there)
            return

        # Detect "/" character to show suggestions immediately
        if event.character == "/":
            # Show suggestions after the slash is inserted
            def show_if_slash_still_there():
                if self.text.strip().startswith("/"):
                    self._show_suggestion_popup()

            self.set_timer(0.01, show_if_slash_still_there)
            return

        # Close suggestions if backspace removes the "/" or "@"
        if event.key == "backspace":
            current_text = self.text
            if not current_text.strip().startswith("/"):
                self._close_suggestion_overlay()
            elif self._suggestion_overlay:
                query = current_text.strip()[1:]
                self._suggestion_overlay.filter_commands(query)

            if "@" not in current_text:
                self._close_file_overlay()
            elif self._file_overlay:
                # Find the current @ mention being typed
                at_index = current_text.rfind("@")
                query = (
                    current_text[at_index + 1 :].split()[0] if at_index != -1 else ""
                )
                self._file_overlay.filter_files(query)

        # Update suggestions as user types
        if self._suggestion_overlay:
            current_text = self.text.strip()
            if current_text.startswith("/"):
                query = current_text[1:]
                self._suggestion_overlay.filter_commands(query)
            else:
                self._close_suggestion_overlay()

        if self._file_overlay:
            current_text = self.text
            at_index = current_text.rfind("@")
            if at_index != -1:
                # Get text from @ until space or end
                mention_text = current_text[at_index + 1 :]
                query = mention_text.split()[0] if mention_text else ""
                self._file_overlay.filter_files(query)
            else:
                self._close_file_overlay()

    def _show_suggestion_popup(self) -> None:
        """Show the visual suggestion overlay."""
        if not self._commands:
            return

        current_text = self.text.strip()
        if not current_text.startswith("/"):
            return

        # Don't show if already visible
        if self._suggestion_overlay:
            return

        def on_select(command: str):
            """Handle command selection from overlay."""
            self.text = f"/{command} "
            self.cursor_position = len(self.text)
            self._close_suggestion_overlay()

        def on_close():
            """Handle overlay close."""
            self._close_suggestion_overlay()

        # Get the query for initial filtering
        query = current_text[1:] if len(current_text) > 1 else ""

        # Get canonical commands mapping from the command processor
        canonical_commands = None
        try:
            from agent_terminal_ui.commands import CommandProcessor

            if hasattr(self.app, "_cmd_processor") and isinstance(
                self.app._cmd_processor, CommandProcessor
            ):
                canonical_commands = self.app._cmd_processor.canonical_commands
        except Exception as e:
            logger.debug(f"Failed to get canonical commands: {e}")

        self._suggestion_overlay = CommandSuggestionsOverlay(
            self._commands,
            on_select,
            on_close,
            initial_query=query,
            canonical_commands=canonical_commands,
        )

        # Mount the overlay in the app
        try:
            app = self.app
        except AttributeError as e:
            logger.debug(f"Using screen.app as fallback: {e}")
            app = self.screen.app if hasattr(self, "screen") else None

        if app:
            app.mount(self._suggestion_overlay)

    def _show_command_suggestions(self) -> None:
        """Show command suggestions based on current input (tab completion)."""
        if not self._commands:
            return

        current_text = self.text.strip()
        if not current_text.startswith("/"):
            return

        # Find matching commands
        matches = [
            cmd
            for cmd in self._commands.keys()
            if cmd.startswith(current_text[1:]) and cmd != current_text[1:]
        ]

        if not matches:
            return

        # Get canonical commands mapping
        canonical_commands = None
        try:
            from agent_terminal_ui.commands import CommandProcessor

            if hasattr(self.app, "_cmd_processor") and isinstance(
                self.app._cmd_processor, CommandProcessor
            ):
                canonical_commands = self.app._cmd_processor.canonical_commands
        except Exception as e:
            logger.debug(f"Failed to get canonical commands: {e}")

        # Auto-complete if only one match
        if len(matches) == 1:
            # Use canonical command name if available
            canonical_match = (
                canonical_commands.get(matches[0], matches[0])
                if canonical_commands
                else matches[0]
            )
            self.text = f"/{canonical_match} "
            self.cursor_position = len(self.text)
            self._close_suggestion_overlay()
        else:
            # Show suggestion overlay
            self._show_suggestion_popup()

    def _update_suggestion_popup(self) -> None:
        """Update or create the suggestion overlay with matching commands."""
        # This is now handled by _show_suggestion_popup
        self._show_suggestion_popup()

    def _show_file_popup(self) -> None:
        """Show the visual file suggestion overlay."""
        current_text = self.text
        at_index = current_text.rfind("@")
        if at_index == -1:
            return

        # Don't show if already visible
        if self._file_overlay:
            return

        def on_select(filename: str):
            """Handle file selection from overlay."""
            current = self.text
            at_idx = current.rfind("@")
            if at_idx != -1:
                # Find the end of the current mention (next space or end)
                mention_part = current[at_idx:]
                space_idx = mention_part.find(" ")
                if space_idx != -1:
                    new_text = (
                        current[:at_idx]
                        + "@"
                        + filename
                        + current[at_idx + space_idx :]
                    )
                else:
                    new_text = current[:at_idx] + "@" + filename + " "

                self.text = new_text
                self.cursor_position = at_idx + len(filename) + 2
            self._close_file_overlay()

        def on_close():
            """Handle overlay close."""
            self._close_file_overlay()

        # Get the query for initial filtering
        mention_text = current_text[at_index + 1 :]
        query = mention_text.split()[0] if mention_text else ""

        self._file_overlay = FileSuggestionsOverlay(
            on_select,
            on_close,
            initial_query=query,
        )

        app = getattr(self, "app", None) or (
            self.screen.app if hasattr(self, "screen") else None
        )
        if app:
            app.mount(self._file_overlay)

    def _show_file_suggestions(self) -> None:
        """Show file suggestions based on current input (tab completion)."""
        current_text = self.text
        at_index = current_text.rfind("@")
        if at_index == -1:
            return

        # Extract the current query

        # If we have an overlay, it handles selection. If not, maybe show it.
        if not self._file_overlay:
            self._show_file_popup()

    def _close_file_overlay(self) -> None:
        """Close the file suggestion overlay if it's open."""
        if self._file_overlay:
            try:
                self._file_overlay.remove()
            except Exception as e:
                logger.debug(f"Failed to remove file overlay: {e}")
            self._file_overlay = None

    def _close_suggestion_overlay(self) -> None:
        """Close the suggestion overlay if it's open."""
        if self._suggestion_overlay:
            try:
                self._suggestion_overlay.remove()
            except Exception as e:
                logger.debug(f"Failed to remove suggestion overlay: {e}")
            self._suggestion_overlay = None
            self._show_suggestions = False
