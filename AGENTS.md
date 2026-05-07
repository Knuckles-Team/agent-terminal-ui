# General Instructions

> **Notice:** This project uses **Spec-Driven Development (SDD)**.
> - Project constitution and governance: `.specify/memory/constitution.md`.
> - Feature specifications and tasks: `.specify/specs/` and `.specify/tasks/`.
> This file (`AGENTS.md`) is for system-prompt context; the SDD directory is the source of truth for architecture and new features.

<!-- Ecosystem Concepts (cross-project, from agent-utilities kernel) -->
<!-- CONCEPT:ECO-4.7 Ecosystem Topology Map — classified as FrontendPackage -->
<!-- CONCEPT:KG-2.13 Cross-Session Chat Recall — consumed via kernel API -->
<!-- CONCEPT:KG-2.14 Project-Aware Context — AGENTS.md auto-loaded by kernel -->
<!-- CONCEPT:KG-2.19 Cross-Pillar Synergy Engine — topology consumer -->
- This is a production-grade Python package. You must *always* follow best open-source Python practices.
- Shortcuts are not appropriate. When in doubt, you must work with the user for guidance.
- Any documentation you write, including in the README.md, should be clear, concise, and accurate like the official documentation of other production-grade Python packages.
- Make sure any comments in code are necessary. A necessary comment captures intent that cannot be encoded in names, types, or structure. Comments should be reserved for the "why", only used to record rationale, trade-offs, links to specs/papers, or non-obvious domain insights. They should add signal that code cannot.
- The current code in the package should be treated as an example of high quality code. Make sure to follow its style and tackle issues in similar ways where appropriate.
- Anything is possible. Do not blame external factors after something doesn't work on the first try. Instead, investigate and test assumptions through debugging through first principles.

# Python Development Instructions
- `ty` by Astral is used for type checking. Always add appropriate type hints such that the code would pass ty's type check.
- Follow the Google Python Style Guide.
- After each code change, checks are automatically run. Fix any issues that arise.
- **IMPORTANT**: The checks will remove any unused imports after you make an edit to a file. So if you need to use a new import, be sure to use it FIRST (or do your edits at the same time) or else it will be automatically removed. DO NOT use local imports to get around this.
- Always prefer pathlib for dealing with files. Use `Path.open` instead of `open`.
- When using pathlib, **always** Use `.parents[i]` syntax to go up directories instead of using `.parent` multiple times.
- When writing tests, use pytest and pytest-asyncio.
- Prefer using loguru for logging instead of the built-in logging module. Do not add logging unless requested.
- NEVER use `# type: ignore`. It is better to leave the issue and have the user work with you to fix it.
- Don't put types in quotes unless it is absolutely necessary to avoid circular imports and forward references.

# Documentation Instructions
- Keep it very concise
- No emojis or em dashes.

# Key Files

@README.md

@pyproject.toml

## New Modules (DeepSeek-TUI Parity)

- **session_manager.py** (TUI-1) -- SQLite-backed session persistence, checkpoints, crash recovery, offline queue
- **workspace_snapshots.py** (TUI-2) -- Side-git workspace snapshots for turn-level rollback
- **reasoning.py** (TUI-3) -- Reasoning effort tiers (OFF/HIGH/MAX) and auto model routing
- **compaction.py** (TUI-4) -- Multi-tier context compaction engine (L1/L2/L3/Cycle)
- **task_manager.py** (TUI-5) -- Durable task queue with SQLite persistence and bounded concurrency
- **hooks.py** (TUI-6) -- Lifecycle hooks with TOML config and timeout-protected execution
- **notifications.py** (TUI-7) -- Desktop notifications via OSC 9/BEL
- **workspace_policy.py** (TUI-8) -- Workspace boundary enforcement and trust mode
- **cost_tracker.py** (TUI-10) -- Per-turn cost tracking with pricing registry
- **danger.py** (TUI-11) -- Extended with ApprovalPolicy/ApprovalEngine
- **shell.py** (TUI-12) -- Extended with JobRecord/JobCenter

## Detailed Documentation

For comprehensive documentation, see the `docs/` directory:

- **[Architecture](docs/architecture.md)** -- Protocols, key components, environment variables, implementation details
- **[Features](docs/features.md)** -- Slash commands, keyboard shortcuts, model picker
- **[Agents & Issues](docs/agents.md)** -- Known issues, recent changes, session journal
- **[Session Management](docs/session_management.md)** -- Session persistence, crash recovery, snapshots
- **[Configuration](docs/configuration.md)** -- Settings reference, hooks config, sandbox modes
