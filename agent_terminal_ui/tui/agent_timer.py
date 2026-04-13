#!/usr/bin/python
# coding: utf-8
"""Agent Activity Timer component.

Provides a visual timer and animated spinner to indicate the agent's
current processing state and execution time.
"""

from time import monotonic

from textual.timer import Timer
from textual.widgets import Static

SPINNER_FRAMES: list[str] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class AgentTimer(Static):
    """Animated timer widget showing agent working status.

    Displays an elapsed time clock and an animation to give visual feedback
    that the agent is actively processing a request.
    """

    def __init__(self) -> None:
        """Initialize the agent timer state."""
        super().__init__()
        self._start_time: float = 0.0
        self._elapsed: float = 0.0
        self._frame_index: int = 0
        self._timer: Timer | None = None
        self._is_running: bool = False

    def on_mount(self) -> None:
        """Configure the widget when it is first mounted."""
        self.display = False

    def start(self) -> None:
        """Initialize and start the activity timer."""
        if self._timer:
            self._timer.stop()
        self._start_time = monotonic()
        self._frame_index = 0
        self._is_running = True
        self.display = True
        self._timer = self.set_interval(0.1, self._tick)

    def stop(self) -> None:
        """Stop the timer and preserve the final elapsed time display."""
        if self._timer:
            self._timer.stop()
            self._timer = None
        self._elapsed = monotonic() - self._start_time
        self._is_running = False
        self._update_display()

    def hide(self) -> None:
        """Stop the timer and hide the widget from view."""
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.display = False

    def _tick(self) -> None:
        """Update the animation frame and elapsed time every 100ms."""
        self._frame_index = (self._frame_index + 1) % len(SPINNER_FRAMES)
        self._elapsed = monotonic() - self._start_time
        self._update_display()

    def _update_display(self) -> None:
        """Calculate and update the widget's visual text."""
        minutes = int(self._elapsed // 60)
        seconds = int(self._elapsed % 60)

        if self._is_running:
            spinner = SPINNER_FRAMES[self._frame_index]
            self.update(f"[dim]{spinner} Working ({minutes}:{seconds:02d})[/dim]")
        else:
            if minutes > 0:
                self.update(f"[dim]Agent worked for {minutes} min {seconds} sec[/dim]")
            else:
                self.update(f"[dim]Agent worked for {seconds} sec[/dim]")
