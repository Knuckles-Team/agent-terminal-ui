#!/usr/bin/python
"""Exit confirmation modal screen.

This module provides a proper Textual ModalScreen implementation for exit confirmation,
following Textual's recommended patterns for focus management and keyboard navigation.
"""

from textual import events
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Label


class ClickableLabel(Label):
    """A label that behaves like a button for text rendering."""

    can_focus = True

    class Clicked(Message):
        """Message sent when the clickable label is clicked."""

        def __init__(self, label: "ClickableLabel") -> None:
            super().__init__()
            self.label = label

    def on_click(self, event: events.Click) -> None:
        """Handle click events."""
        self.post_message(self.Clicked(self))

    def on_key(self, event: events.Key) -> None:
        """Handle key events for keyboard navigation."""
        if event.key == "enter":
            self.post_message(self.Clicked(self))
            event.prevent_default()
        elif event.key == "tab":
            # Let tab handle focus navigation normally
            pass
        elif event.key in ["up", "down", "left", "right"]:
            # Let arrow keys handle focus navigation normally
            pass


class ExitConfirmScreen(ModalScreen[bool]):
    """Exit confirmation modal screen.

    This modal provides a proper Textual implementation with:
    - Focusable Button widgets
    - Proper keyboard navigation (Tab, arrows, Esc)
    - Clean lifecycle management via dismiss()
    - Returns boolean result (True = exit, False = cancel)
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("y", "confirm_exit", "Yes", show=False),
        Binding("n", "cancel", "No", show=False),
    ]

    DEFAULT_CSS = """
    ExitConfirmScreen {
        align: center middle;
    }

    #dialog {
        width: auto;
        max-width: 90;
        height: auto;
        padding: 2;
        border: round $primary;
        background: $surface;
    }

    #question {
        margin-bottom: 1;
        text-align: center;
        text-style: bold;
        color: $primary;
    }

    #buttons {
        align-horizontal: center;
    }

    ClickableLabel {
        margin: 0 1;
        padding: 1 2;
        text-style: bold;
        background: $primary;
        color: $background;
        border: solid $primary;
    }

    ClickableLabel#yes {
        background: $error;
        border: solid $error;
        color: #ffffff;
    }

    ClickableLabel#no {
        background: $success;
        border: solid $success;
        color: #000000;
    }

    ClickableLabel:hover {
        opacity: 0.8;
    }

    ClickableLabel:focus {
        border: double $primary;
        text-style: bold underline;
    }

    ClickableLabel#yes:focus {
        border: double $error;
    }

    ClickableLabel#no:focus {
        border: double $success;
    }
    """

    def __init__(self, callback=None) -> None:
        """Initialize the exit confirmation screen.

        Args:
            callback: Optional callback function to call with the result (bool).
        """
        super().__init__()
        self._callback = callback

    def compose(self):
        """Compose the modal with confirmation dialog."""
        with Vertical(id="dialog"):
            yield Label("Are you sure you want to exit?", id="question")
            with Horizontal(id="buttons"):
                yield ClickableLabel("Yes, exit", id="yes")
                yield ClickableLabel("No, continue", id="no")

    def on_mount(self) -> None:
        """Set initial focus to the No button (safer default)."""
        self.set_focus(None, "#no")

    def action_confirm_exit(self) -> None:
        """Confirm exit action (Y key)."""
        self._dismiss_with_callback(True)

    def action_cancel(self) -> None:
        """Cancel the confirmation and return False."""
        self._dismiss_with_callback(False)

    def on_clickable_label_clicked(self, event: ClickableLabel.Clicked) -> None:
        """Handle clickable label click events."""
        if event.label.id == "yes":
            self._dismiss_with_callback(True)
        else:  # no button or cancel
            self._dismiss_with_callback(False)

    def _dismiss_with_callback(self, result: bool) -> None:
        """Dismiss the screen and call the callback with the result."""
        try:
            if self._callback:
                self._callback(result)
        except Exception as e:
            # Log error but don't prevent dismissal
            import logging

            logging.getLogger(__name__).error(f"Error in exit callback: {e}")
        finally:
            self.dismiss(result)
