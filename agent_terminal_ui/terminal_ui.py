#!/usr/bin/python
"""CLI entry point for the Agent Terminal UI.

This module provides the ``agent-tui`` console script referenced
in ``pyproject.toml``.  It delegates immediately to :func:`app.main`.
"""

from agent_terminal_ui.app import main


def terminal_ui() -> None:
    """Launch the Agent Terminal UI application."""
    main()


if __name__ == "__main__":
    terminal_ui()
