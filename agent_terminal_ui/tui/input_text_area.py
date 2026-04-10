from textual import events
from textual.message import Message
from textual.widgets import TextArea


class InputTextArea(TextArea):
    """TextArea that handles Enter for submit and Shift+Enter for newline."""

    class Submitted(Message):
        """Posted when user presses Enter to submit."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_key_was_backslash = False

    def on_key(self, event: events.Key) -> None:
        # Some terminals sends backslash followed by enter as two separate events for
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
            # TODO: This is not great if you actually wanted to type a backslash
            # User typed backslash followed by another key (not enter), so they
            # actually wanted a literal backslash
            self.insert("\\")
            self._last_key_was_backslash = False
