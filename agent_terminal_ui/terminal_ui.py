#!/usr/bin/python
"""CLI entry point for the Agent Terminal UI.

This module provides the ``agent-terminal-ui`` console script referenced
in ``pyproject.toml``.  It delegates immediately to :func:`app.main`.
"""

from agent_terminal_ui.app import main


def terminal_ui() -> None:
    """Launch the Agent Terminal UI application."""
    import argparse

    parser = argparse.ArgumentParser(description="Agent Terminal UI")
    parser.add_argument(
        "--prompt", type=str, help="Initial prompt to send to the agent"
    )
    parser.add_argument(
        "--override",
        action="store_true",
        help="Auto-approve all tool calls (yolo mode)",
    )
    parser.add_argument(
        "--bg", action="store_true", help="Start session in background (agent view)"
    )
    args = parser.parse_args()
    main(initial_prompt=args.prompt, auto_approve=args.override, start_bg=args.bg)


if __name__ == "__main__":
    terminal_ui()
