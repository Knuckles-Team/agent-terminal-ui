"""Guards the frontend's lightweight footprint.

The terminal UI must talk to the backend over HTTP, never import the heavy
``agent_utilities`` package (which drags in the KG engine, logfire, opentelemetry,
and an embedding model) into its own process. Importing the app and driving the
core interactive paths must keep those modules out of ``sys.modules`` so a single
instance stays in the tens-of-MB range rather than ballooning to gigabytes.

See: reports/agent-terminal-ui-baseline-2026-06-11.md
"""

import subprocess
import sys

# Heavy modules that must never be pulled into a frontend instance.
FORBIDDEN = (
    "agent_utilities",
    "torch",
    "transformers",
    "sentence_transformers",
    "tensorflow",
)


def _run_probe(body: str) -> set[str]:
    """Run ``body`` in a clean interpreter; return forbidden modules it imported."""
    script = (
        "import sys\n"
        f"{body}\n"
        f"forbidden = {FORBIDDEN!r}\n"
        "leaked = sorted(m for m in sys.modules "
        "if any(m == f or m.startswith(f + '.') for f in forbidden))\n"
        "print('\\n'.join(leaked))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return {line for line in out.stdout.splitlines() if line}


def test_importing_app_does_not_import_backend() -> None:
    """A bare ``import agent_terminal_ui.app`` stays free of heavy backend libs."""
    leaked = _run_probe("import agent_terminal_ui.app")
    assert leaked == set(), f"frontend import leaked heavy modules: {sorted(leaked)}"


def test_goal_parsing_does_not_import_backend() -> None:
    """``/goal`` parsing uses the vendored spec, not ``agent_utilities``."""
    leaked = _run_probe(
        "from agent_terminal_ui.goal import GoalSpec\n"
        "GoalSpec.parse_goal_input('fix tests until pytest passes without touching db')"
    )
    assert leaked == set(), f"goal parsing leaked heavy modules: {sorted(leaked)}"
