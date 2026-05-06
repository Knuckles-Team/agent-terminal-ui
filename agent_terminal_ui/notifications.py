"""Desktop notifications for long-running turns.

Emits OSC 9 or BEL escape sequences when a turn completes after
exceeding a configurable time threshold.

Concept: TUI-7 (Desktop Notifications)
"""

from __future__ import annotations

import logging
import os
import sys
from enum import Enum

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD_SECS = 30


class NotificationMethod(Enum):
    """Notification delivery method."""

    AUTO = "auto"
    OSC9 = "osc9"
    BEL = "bel"
    OFF = "off"


def _detect_method() -> NotificationMethod:
    """Auto-detect the best notification method for the terminal."""
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    term = os.environ.get("TERM", "").lower()

    # OSC 9 is supported by iTerm2, Ghostty, WezTerm, Kitty
    osc9_terminals = {
        "iterm.app",
        "iterm2",
        "ghostty",
        "wezterm",
        "kitty",
    }  # codespell:ignore iterm
    if term_program in osc9_terminals:
        return NotificationMethod.OSC9

    # Terminal.app 13+ supports OSC 9 but detection is unreliable
    if term_program == "apple_terminal":
        return NotificationMethod.OSC9

    # Check for known capable terminals via TERM
    if any(t in term for t in ("xterm", "screen", "tmux")):
        return NotificationMethod.BEL

    # Fallback to BEL on Linux/macOS, off on Windows
    if sys.platform == "win32":
        return NotificationMethod.OFF
    return NotificationMethod.BEL


class DesktopNotifier:
    """Emits desktop notifications on long-running turn completion.

    Only fires on successful turn completions that exceed the configured
    time threshold. Failed or cancelled turns are intentionally silent.
    """

    def __init__(
        self,
        method: NotificationMethod | str = NotificationMethod.AUTO,
        threshold_secs: int = DEFAULT_THRESHOLD_SECS,
        include_summary: bool = False,
    ) -> None:
        """Initialize the desktop notifier.

        Args:
            method: Notification method (auto, osc9, bel, off).
            threshold_secs: Minimum turn duration to trigger notification.
            include_summary: Include elapsed time and cost in notification.
        """
        if isinstance(method, str):
            method = NotificationMethod(method)
        self._method = method
        self._threshold_secs = threshold_secs
        self._include_summary = include_summary
        self._resolved_method: NotificationMethod | None = None

    @property
    def method(self) -> NotificationMethod:
        return self._method

    @property
    def threshold_secs(self) -> int:
        return self._threshold_secs

    @threshold_secs.setter
    def threshold_secs(self, value: int) -> None:
        self._threshold_secs = max(1, value)

    def _resolve_method(self) -> NotificationMethod:
        """Resolve AUTO to a concrete method."""
        if self._resolved_method is not None:
            return self._resolved_method

        if self._method == NotificationMethod.AUTO:
            self._resolved_method = _detect_method()
        else:
            self._resolved_method = self._method
        return self._resolved_method

    def notify_turn_complete(
        self,
        elapsed_secs: float,
        cost_usd: float = 0.0,
        success: bool = True,
    ) -> bool:
        """Notify on turn completion if threshold is met.

        Args:
            elapsed_secs: Turn duration in seconds.
            cost_usd: Optional cost in USD.
            success: Whether the turn completed successfully.

        Returns:
            True if a notification was emitted.
        """
        # Only notify on success
        if not success:
            return False

        # Check threshold
        if elapsed_secs < self._threshold_secs:
            return False

        method = self._resolve_method()
        if method == NotificationMethod.OFF:
            return False

        # Build notification message
        message = "Agent turn complete"
        if self._include_summary:
            parts = [f"{elapsed_secs:.1f}s"]
            if cost_usd > 0:
                parts.append(f"${cost_usd:.4f}")
            message = f"Agent turn complete ({', '.join(parts)})"

        return self._emit(method, message)

    def _emit(self, method: NotificationMethod, message: str) -> bool:
        """Emit the notification escape sequence.

        Args:
            method: The resolved notification method.
            message: The notification message.

        Returns:
            True if emission succeeded.
        """
        try:
            if method == NotificationMethod.OSC9:
                # OSC 9: iTerm2-style notification
                sys.stdout.write(f"\x1b]9;{message}\x07")
                sys.stdout.flush()
                return True
            elif method == NotificationMethod.BEL:
                # Simple BEL character
                sys.stdout.write("\x07")
                sys.stdout.flush()
                return True
        except OSError as e:
            logger.debug(f"Failed to emit notification: {e}")

        return False

    def test(self) -> bool:
        """Emit a test notification.

        Returns:
            True if the test notification was emitted.
        """
        method = self._resolve_method()
        if method == NotificationMethod.OFF:
            return False
        return self._emit(method, "Test notification from Agent Terminal UI")
