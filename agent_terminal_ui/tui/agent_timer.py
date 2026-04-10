from time import monotonic

from textual.timer import Timer
from textual.widgets import Static

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class AgentTimer(Static):
    """Animated timer showing agent working status."""

    def __init__(self) -> None:
        super().__init__()
        self._start_time: float = 0.0
        self._elapsed: float = 0.0
        self._frame_index: int = 0
        self._timer: Timer | None = None
        self._is_running: bool = False

    def on_mount(self) -> None:
        self.display = False

    def start(self) -> None:
        if self._timer:
            self._timer.stop()
        self._start_time = monotonic()
        self._frame_index = 0
        self._is_running = True
        self.display = True
        self._timer = self.set_interval(0.1, self._tick)

    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
            self._timer = None
        self._elapsed = monotonic() - self._start_time
        self._is_running = False
        self._update_display()

    def hide(self) -> None:
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.display = False

    def _tick(self) -> None:
        """Called every 0.1 seconds to update animation."""
        self._frame_index = (self._frame_index + 1) % len(SPINNER_FRAMES)
        self._elapsed = monotonic() - self._start_time
        self._update_display()

    def _update_display(self) -> None:
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
