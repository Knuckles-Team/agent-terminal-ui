"""Shell terminal widget for the TUI.

Provides an interactive terminal widget that renders ANSI output
from a PTY shell session within the Textual application.

Concept: AU-018 (Shell Terminal Widget)
"""

from __future__ import annotations

import asyncio
import logging

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalGroup
from textual.reactive import var
from textual.widgets import RichLog, Static

from agent_terminal_ui.shell import Shell

logger = logging.getLogger(__name__)


class ShellTerminal(VerticalGroup):
    """Interactive terminal widget backed by a PTY shell.

    Renders shell output with ANSI color support and provides
    keyboard input forwarding to the underlying shell process.
    """

    DEFAULT_CSS = """
    ShellTerminal {
        height: auto;
        min-height: 4;
        max-height: 20;
        background: $surface;
        border: solid $primary 30%;
        padding: 0;
        margin: 0 1 1 1;
    }

    ShellTerminal .shell-header {
        height: 1;
        background: $primary 20%;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }

    ShellTerminal .shell-output {
        height: auto;
        min-height: 3;
        max-height: 18;
        background: $surface;
        padding: 0 1;
        color: $text;
        overflow-y: auto;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "send_interrupt", "Interrupt", show=False),
    ]

    active: var[bool] = var(False)

    def __init__(
        self,
        shell: Shell,
        *,
        title: str = "Shell",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the shell terminal.

        Args:
            shell: The Shell instance to render.
            title: Title for the terminal header.
            name: Optional Textual name.
            id: Optional Textual id.
            classes: Optional Textual CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._shell = shell
        self._title = title
        self._read_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        """Compose the terminal layout."""
        yield Static(
            f"[$primary]▸[/$primary] {self._title} — {self._shell.cwd}",
            classes="shell-header",
            markup=True,
        )
        yield RichLog(
            classes="shell-output",
            wrap=True,
            markup=True,
            auto_scroll=True,
        )

    async def on_mount(self) -> None:
        """Start the shell and begin reading output."""
        if not self._shell.running:
            self._shell.start()
        self.active = True
        self._start_reading()

    def on_unmount(self) -> None:
        """Stop reading when unmounted."""
        self.active = False

    @work(exclusive=True)
    async def _start_reading(self) -> None:
        """Background worker to read shell output."""
        output_log = self.query_one(".shell-output", RichLog)

        while self.active and self._shell.running:
            data = await self._shell.read_async(timeout=0.05)
            if data:
                # Strip ANSI escape sequences for basic rendering
                # (full ANSI support can be added with a terminal emulator library)
                cleaned = self._strip_ansi(data)
                if cleaned.strip():
                    output_log.write(cleaned)
            else:
                await asyncio.sleep(0.05)

    def action_send_interrupt(self) -> None:
        """Send Ctrl+C to the shell."""
        self._shell.send_interrupt()

    def send_input(self, text: str) -> None:
        """Send text input to the shell.

        Args:
            text: The text to send (typically ends with newline).
        """
        self._shell.write(text)

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """Strip ANSI escape sequences from text.

        Args:
            text: Text potentially containing ANSI sequences.

        Returns:
            Clean text without ANSI codes.
        """
        import re

        ansi_escape = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07")
        return ansi_escape.sub("", text)
