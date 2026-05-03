"""Animated thinking indicator widget.

Provides a subtle, inline throbber that displays within the conversation
flow to indicate the agent is processing. Replaces the AgentTimer bar
with a more integrated visual.

Concept: AU-018 (Conversation UX)
"""

from textual.reactive import var
from textual.widgets import Static

THROBBER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Throbber(Static):
    """An animated thinking indicator that appears inline in the conversation.

    Shows a spinning indicator with configurable text while the agent
    is processing a request.
    """

    DEFAULT_CSS = """
    Throbber {
        height: 1;
        margin: 0 0 1 1;
        color: $text-muted;
        display: none;
    }

    Throbber.-active {
        display: block;
    }
    """

    active: var[bool] = var(False, init=False)
    _frame_index: int = 0
    _timer_handle = None

    def __init__(
        self,
        label: str = "Thinking",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the throbber.

        Args:
            label: Text to display next to the spinner.
            name: Optional Textual name.
            id: Optional Textual id.
            classes: Optional Textual CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._label = label

    def start(self, label: str | None = None) -> None:
        """Start the throbber animation.

        Args:
            label: Optional new label text.
        """
        if label:
            self._label = label
        self.active = True
        self.set_class(True, "-active")
        self._frame_index = 0
        self._update_display()
        if self._timer_handle is None:
            self._timer_handle = self.set_interval(0.1, self._advance_frame)

    def stop(self) -> None:
        """Stop the throbber animation and hide it."""
        self.active = False
        self.set_class(False, "-active")
        if self._timer_handle is not None:
            self._timer_handle.stop()
            self._timer_handle = None

    def _advance_frame(self) -> None:
        """Advance to the next animation frame."""
        if not self.active:
            return
        self._frame_index = (self._frame_index + 1) % len(THROBBER_FRAMES)
        self._update_display()

    def _update_display(self) -> None:
        """Update the displayed text."""
        frame = THROBBER_FRAMES[self._frame_index]
        self.update(f"[$warning]{frame}[/$warning] {self._label}...")
