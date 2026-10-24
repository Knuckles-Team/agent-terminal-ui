# Contributing

Read [AGENTS.md](AGENTS.md) and the owning requirement in `specs/terminal-runtime/` before editing.
Use a separate Git worktree. Keep unrelated changes intact and stage explicit paths.

## Tools and setup

The package requires Python 3.12 or newer. `.python-version` selects the development interpreter.
Use uv for the locked environment and pre-commit 4.6.0 for repository checks.
Install the test extra; `--all-groups` alone does not install optional test dependencies.

```bash
uv sync --frozen --extra test
uv run --frozen --extra test pytest tests/test_source_quality.py -q
uvx --from pre-commit==4.6.0 pre-commit run --all-files
```

The focused command checks the credential-free environment example.
Choose the affected test modules for other changes. Run the configured gates before committing.
The pre-commit configuration owns formatter, lint, type and security tool versions.
Standalone ruff or ty executables are not supplied by the runtime installation.
Dependency changes also require the repository's lock validation; do not bypass a failed gate.

## Source map

| Path | Responsibility |
|---|---|
| `agent_terminal_ui/terminal_ui.py` | Installed command argument parsing and dispatch. |
| `agent_terminal_ui/app.py` | Application lifecycle and event coordination. |
| `agent_terminal_ui/screens/` | Screen composition, focus and layout. |
| `agent_terminal_ui/widgets/` | Conversation and other reusable widgets. |
| `agent_terminal_ui/tui/` | Modal screens, input and presentation helpers. |
| `agent_terminal_ui/client.py` | Served Arbora client adapter. |
| `native/agent-terminal-ui/` | Separate native terminal implementation. |
| `tests/` | Unit, mounted, integration and terminal regression fixtures. |
| `specs/terminal-runtime/` | Requirements, tasks, acceptance evidence and generated status. |
| `docs/` | Detailed operator documentation published with MkDocs. |

## Evidence and publication

Record completed checks and unproven acceptance criteria in the owning test specification.
Source tests do not replace installed-command, live-service or native performance qualification.
Generate canonical spec status after implementation commits and check freshness before publication.
Follow the repository's review process; do not claim skipped checks as passes.
