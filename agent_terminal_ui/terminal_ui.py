#!/usr/bin/python
"""CLI entry point for the Agent Terminal UI.

This module provides the ``agent-terminal-ui`` console script referenced in
``pyproject.toml``. The Textual application is imported lazily so that headless
runs (``--headless``) stay lightweight and never load the TUI widget tree.
"""


def terminal_ui() -> None:
    """Launch the Agent Terminal UI, or run a single prompt headlessly."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Agent Terminal UI", allow_abbrev=False
    )
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
        "--model",
        type=str,
        default=None,
        help="Compatibility option; ignored by the A2A transport "
        "(server selects model)",
    )
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Reuse this context ID; does not load prior turns for the model",
    )
    parser.add_argument(
        "--observe-task",
        type=str,
        help="Read an existing task without submission or approval",
    )
    args = parser.parse_args()

    if args.observe_task is not None:
        if (
            not args.observe_task.strip()
            or len(args.observe_task) > 512
            or args.prompt is not None
            or args.override
            or args.bg
            or args.model is not None
            or args.session is not None
        ):
            parser.error(
                "--observe-task requires a task ID and cannot combine with turn options"
            )
        import asyncio

        from agent_terminal_ui.headless import run_task_observer

        try:
            ok = asyncio.run(run_task_observer(args.observe_task))
        except KeyboardInterrupt:
            raise SystemExit(130) from None
        if not ok:
            raise SystemExit(1)
        return

    if args.headless:
        if not args.prompt:
            parser.error("--headless requires --prompt")
        import asyncio

        from agent_terminal_ui.headless import run_headless

        ok = asyncio.run(
            run_headless(
                args.prompt,
                model=args.model,
                session_id=args.session,
            )
        )
        if not ok:
            raise SystemExit(1)
        return

    from agent_terminal_ui.app import main

    main(
        initial_prompt=args.prompt,
        auto_approve=args.override,
        start_bg=args.bg,
        session_id=args.session,
    )


if __name__ == "__main__":
    terminal_ui()
