# General Instructions

> Claude Code loads this file via `CLAUDE.md` (`@AGENTS.md` import) — the two stay in sync. Edit this file, not `CLAUDE.md`.


> **Notice:** This project uses **Spec-Driven Development (SDD)**.
> - Project constitution and governance: `.specify/memory/constitution.md`.
> - Feature specifications and tasks: `.specify/specs/` and `.specify/tasks/`.
> This file (`AGENTS.md`) is for system-prompt context; the SDD directory is the source of truth for architecture and new features.

<!-- Ecosystem Concepts (cross-project, from agent-utilities kernel) -->
<!-- CONCEPT:AU-OS.deployment.infra-orchestration Ecosystem Topology Map — classified as FrontendPackage -->
<!-- CONCEPT:AU-KG.memory.background-learning-engine Cross-Session Chat Recall — consumed via kernel API -->
<!-- CONCEPT:AU-KG.memory.ground-truth-preamble-declaring Project-Aware Context — AGENTS.md auto-loaded by kernel -->
<!-- CONCEPT:AU-KG.temporal.bi-temporal-memory-layers Cross-Pillar Synergy Engine — topology consumer -->
<!-- CONCEPT:AU-ECO.toolkit.journey-map-milestones Terminal Agent Launcher — --prompt and --override CLI flags for tmux-spawned one-shot execution -->
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
- **screens/agent_view.py** (TUI-20) -- Agent View multi-session dashboard with peek panel
- **background_runner.py** (TUI-21) -- Background session runner for detached async agents
- **widgets/goal_status.py** (AU-ORCH.session.durable-session-autonomous-goal) -- Live goal progress widget
- **headless.py** -- `HeadlessRunner` + `StreamSink` + `RenderSink` protocol for the no-widget-tree `--headless` run path (lazy-imported from `terminal_ui.py`)
- **goal.py** -- Dependency-free `GoalSpec` parser for `/goal` (keeps the frontend free of an `agent_utilities` import)
- **tui/animation.py** -- Shared `animate_in()` entrance fade for conversation widgets (honors `TEXTUAL_ANIMATIONS` / reduced motion)
- **screens/dashboard.py** -- Alt+D service dashboard, fed over HTTP via `AgentClient.get_dashboard_full()` (no in-process gateway)

## CLI Flags (AU-ECO.toolkit.journey-map-milestones)

- `--prompt TEXT` -- Inject an initial task on launch. Auto-submitted via `on_mount` once the TUI is ready.
- `--override` -- Yolo mode. Auto-approves all pending tool calls, bypassing `ToolApprovalScreen`.
- `--bg` -- Start in Agent View (background mode). Launches session as background worker.
- `--headless` -- Run `--prompt` without the TUI, streaming output to stdout (`headless.py`: `HeadlessRunner` + `StreamSink`). No Textual is imported, so a headless instance stays light (~30MB) -- the substrate for many concurrent non-interactive sessions against one shared backend. Requires `--prompt`; optional `--model`.

## Detailed Documentation

For comprehensive documentation, see the `docs/` directory:

- **[Architecture](docs/architecture.md)** -- Protocols, key components, environment variables, implementation details
- **[Features](docs/features.md)** -- Slash commands, keyboard shortcuts, model picker
- **[Agents & Issues](docs/agents.md)** -- Known issues, recent changes, session journal
- **[Session Management](docs/session_management.md)** -- Session persistence, crash recovery, snapshots
- **[Configuration](docs/configuration.md)** -- Settings reference, hooks config, sandbox modes
- **[Goal Command](docs/goal_command.md)** -- Autonomous `/goal` loop with KG-native integration
- **[Agent View](docs/agent_view.md)** -- Multi-session dashboard and background agent management

## ⛔ No Scratch or Temporary Files in Repository

**NEVER write any of the following to this repository:**
- Temporary test scripts (`test_*.py`, `debug_*.py` outside of `tests/`)
- Scratch scripts or experimental one-off files
- Log files (`.log`, `.txt` command output)
- Random text files with command output or debug dumps
- Any file that is NOT production source code, tests in `tests/`, or documentation

**Why:** These files expose private filesystem paths, credentials, and internal infrastructure details when pushed to GitHub publicly.

**Where to put scratch work instead:**
- Use `~/workspace/scratch/` for temporary scripts and experiments
- Use `~/workspace/reports/` for command output and reports
- Keep test scripts in the `tests/` directory following proper pytest conventions


## ⛔ Keep the Repository Root Pristine

The repository root must contain only canonical project files. The only hidden
directories allowed at root are `.git/`, `.github/`, `.specify/` (plus a local,
git-ignored `.venv/`). NEVER write scratch/debug/migration files to the repo —
especially the root: no `fix_*.py`/`migrate_*.py`/`refactor_*.py`/root `test_*.py`,
no `*.db`/`*.log`/scratch `*.txt`/`*.orig`/`*.rej`/`*.bak`, no build artifacts
(`*.tsbuildinfo`), and no AI scratch dirs (`.agent/`, `.agents/`, `.agent_data/`,
`.tmp/`, `.hypothesis/`). Put experiments in `~/workspace/scratch/`, tests in
`tests/`. Run `git status` before finishing and confirm no stray root files.

## Working Discipline — think, simplify, stay surgical, verify

These four habits cut the most common LLM coding mistakes. For trivial tasks, use
judgment; the bias here is correctness over speed.

- **Think before coding.** State your assumptions explicitly. If a request has more than
  one reasonable reading, surface the options instead of silently picking one. If a
  simpler approach exists, say so and push back when warranted. When something is
  genuinely unclear, stop and name what's confusing — ask, don't guess.
- **Simplicity first.** Write the minimum code that solves the stated problem — no
  speculative features, no abstraction for single-use code, no configurability that
  wasn't requested, no error handling for impossible states. If you wrote 200 lines and
  it could be 50, rewrite it. (Name code from its purpose, never `wave0`/`phase2`/`v2`.)
- **Stay surgical.** Every changed line should trace directly to the task. Don't refactor,
  reformat, or "improve" working code adjacent to your change; match the existing style
  even where you'd do it differently. Remove only the imports/symbols your own change
  orphaned; if you spot unrelated dead code, mention it rather than deleting it inline.
  *Exception — the Quality Bar below:* lint/format/type errors the pre-commit gate flags
  get fixed regardless of who introduced them. In short: **surgical on behavior, clean on
  lint.**
- **Verify against a goal.** Turn the task into a checkable outcome before you start:
  "fix the bug" → "write a failing test that reproduces it, then make it pass"; "add
  validation" → "tests for the invalid inputs pass". For multi-step work, state the short
  plan and the check for each step, then loop until the checks pass.

## Quality Bar — Leave the Codebase Clean (REQUIRED)

After completing any code change, run the project's pre-commit suite and drive it
**fully green** before committing:

```bash
pre-commit run --all-files
```

Resolve **every** issue it reports — failures, lint errors, type errors, and
warnings — **including problems that pre-date your change and were not caused by
your edits**. The standing goal is a clean, working codebase with **no errors and
no warnings**. Do not silence checks (`# noqa`, `# type: ignore`, `SKIP=`,
`--no-verify`) to force green unless the exception is already documented in this
file as a known, unavoidable limitation. Only commit once `pre-commit run
--all-files` passes cleanly; if a check legitimately cannot pass, stop and explain
why rather than bypassing it.

## Working with Git Worktrees (multi-session)

Multiple agents/sessions work the `agent-packages/*` repos concurrently. **Do not
edit the canonical checkout** (`/home/apps/workspace/agent-packages/<repo>`) — a
background `repository-manager` sync can reset its working tree and discard
uncommitted edits. Take your own git worktree on your own branch instead:

```bash
# preferred — repository-manager MCP:
rm_worktree add <repo> <your-branch>      # -> /home/apps/worktrees/<repo>/<your-branch>

# raw-git fallback:
git -C agent-packages/<repo> checkout main
git -C agent-packages/<repo> worktree add /home/apps/worktrees/<repo>/<branch> -b <branch>
```

Work in the worktree and **commit often** (commits survive a working-tree reset).
Each session must use a **distinct branch** — git allows a branch in only one
worktree, which is what keeps concurrent sessions from colliding. Worktrees live
under `/home/apps/worktrees/` (outside the workspace scan, so the sync leaves them
alone).

**Finishing work in a worktree** — run this sequence before calling it done:
1. **Pre-commit green** — `pre-commit run --all-files`; resolve every issue per the
   Quality Bar above (including pre-existing), no `--no-verify`.
2. **Commit** in the worktree.
3. **Merge to main locally** — `rm_worktree merge <repo> <branch> --into main`
   (or `git merge --no-ff`). Push only when the user asks.
4. **Clean up** — remove the worktree and delete the merged branch:
   `rm_worktree remove <repo> <branch> --delete-branch`; `rm_worktree prune` clears
   stale entries. (Raw-git: `git worktree remove <path> && git branch -d <branch>`.)

<!-- BEGIN concept-coordination (generated) -->
## Concept-ID Coordination (multi-session)

Working in parallel with other sessions/worktrees? **Reserve a concept id before you write its `CONCEPT:` marker** so two sessions never collide:

```bash
agent-utilities --json concept reserve --ns EG-KG.compute.backend   # or a package prefix, e.g. KEY
```

Full protocol (ledger, merge=union, reconcile, MCP/REST): <https://knuckles-team.github.io/agent-utilities/concept_coordination/>
<!-- END concept-coordination (generated) -->

## Version & lockfile drift edict (keep the version mirrors AND the lock in sync)

The two most common release-breakers in this fleet are **version drift** (the version in
`pyproject.toml`/`.bumpversion.cfg` advancing while `README.md`, `docker/Dockerfile`, and the
module `__version__`s lag) and a **stale `uv.lock`** (shipping known-vulnerable transitive deps).
A version mismatch makes the next `bump-my-version` throw `VersionNotFoundException`; a stale lock
is what Dependabot flags. Rules:

1. **Never hand-edit a version string.** Change the version ONLY via
   `bump-my-version bump {patch|minor|major}` (a.k.a. `bump2version`), which rewrites every file
   registered in `.bumpversion.cfg` in one atomic, tagged commit. If you edited the version in
   `pyproject.toml` by hand, you created drift — revert and use the bumper.
2. **Every version-bearing file must be registered in `.bumpversion.cfg`** — at minimum
   `pyproject.toml` AND `README.md`, plus `docker/Dockerfile` and any module `__version__`. Never
   add a file that embeds the version without a `[bumpversion:file:...]` entry for it.
3. **Re-lock on every dependency change.** After editing `pyproject.toml` deps/extras, run
   `uv lock` and commit `uv.lock` in the SAME change. The `uv-lock` pre-commit hook runs with
   `--locked` and fails on drift — never bypass it. The committed `uv.lock` is the
   Dependabot/security surface.
4. **Patch CVEs with a version floor at the source, then re-lock.** `uv` resolves one version
   graph-wide, so a lower-bound in the extra that pulls a dependency raises it for the whole lock.
