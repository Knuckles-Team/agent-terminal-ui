#!/usr/bin/python
"""Input text area component for user queries.

Customization of the Textual TextArea to handle submission on Enter and
properly manage multi-line input via Shift+Enter (or backslash-escaped Enter
on some terminals).
"""

from textual import events
from textual.message import Message
from textual.widgets import TextArea


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

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the input text area.

        Args:
            *args: Positional arguments passed to the base TextArea.
            **kwargs: Keyword arguments passed to the base TextArea.

        """
        super().__init__(*args, **kwargs)
        self._last_key_was_backslash: bool = False

    def on_key(self, event: events.Key) -> None:
        """Handle key events to intercept submission and control newlines.

        Supports a specific heuristic for Shift+Enter emulation:
        - Backslash followed by Enter results in a newline.
        - Plain Enter results in a 'Submitted' message.

        Args:
            event: The Textual key event to process.

        """
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
                self.post_message(self.Submitted(self.text))
            return

        if self._last_key_was_backslash:
            # Handle cases where the user actually intended to type a literal backslash.
            # If any other key follows the backslash, we insert the backslash first.
            self.insert("\\")
            self._last_key_was_backslash = False
