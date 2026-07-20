#!/usr/bin/python
"""CLI entry point for the Agent Terminal UI.

This module provides the ``agent-terminal-ui`` console script referenced in
``pyproject.toml``. The Textual application is imported lazily so that headless
runs (``--headless``) stay lightweight and never load the TUI widget tree.
"""


def terminal_ui() -> None:
    """Launch the Agent Terminal UI, or run a single prompt headlessly."""
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
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run --prompt without the TUI, streaming output to stdout "
        "(lightweight; for non-interactive/automated sessions)",
    )
    parser.add_argument(
        "--model", type=str, default=None, help="Model id for headless runs"
    )
    args = parser.parse_args()

    if args.headless:
        if not args.prompt:
            parser.error("--headless requires --prompt")
        import asyncio

        from agent_terminal_ui.headless import run_headless

        asyncio.run(run_headless(args.prompt, model=args.model))
        return

    from agent_terminal_ui.app import main

    main(initial_prompt=args.prompt, auto_approve=args.override, start_bg=args.bg)


if __name__ == "__main__":
    terminal_ui()
