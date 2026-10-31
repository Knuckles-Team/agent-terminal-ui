# General Instructions

<!-- agent-contract:start -->
## Agent contract

Tool-neutral rules for any AI agent or human working in this repository. The fleet standard maintains this block; edit outside the markers.

- **Owner boundary:** this repository owns the terminal interface (spec prefix `TUI-`). Data reaches it only through arbora. See [ecosystem boundaries](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ecosystem-boundaries.md) for feature routing.
- **Setup:** run `scripts/bootstrap.sh`. The script is idempotent and non-interactive. It ensures uv >= 0.9 and the declared Python version. It syncs the locked environment, installs git hooks and prints the gate command.
- **Gates:** `uvx pre-commit run --all-files` must pass before each push. Do not bypass hooks to get green.
- **Commits:** one logical change per commit with a `Spec: <ID>` trailer (or `Spec: none (<reason>)`), plus a `Co-Authored-By:` trailer naming the assisting agent. Stage explicit paths only; never `git add -A` or `git add .`. Use the contributor's configured Git identity, never a tool or bot name.
- **Org rules:** [organization AGENTS.md](https://github.com/Knuckles-Team/.github/blob/main/AGENTS.md).
<!-- agent-contract:end -->

## Spec-driven development

Every feature starts with a spec, in this order. Read `.specify/memory/constitution.md` first; it inherits the [organization constitution](https://github.com/Knuckles-Team/pipelines/blob/main/.specify/memory/constitution.md). Route the feature with the [ecosystem boundaries](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ecosystem-boundaries.md) and file each part in its owner's `specs/`. Run the flow with the skills in the table (universal-skills). Rules: [spec standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/spec-standard.md); templates: `.specify/templates/`, vended by pipelines.

| Step | Skill | Writes | Checked by |
|---|---|---|---|
| Constitution | `spec-generator` | `.specify/memory/constitution.md` | spec-standard constitution check |
| Specify | `spec-intake-wizard`, `spec-generator` | `specs/<id>/spec.md`, `requirements.md` | spec-standard |
| Clarify | `spec-generator` | resolves each `[NEEDS CLARIFICATION: ...]` marker | spec-standard clarification check |
| Plan | `spec-generator` | `plan.md` (upstream sections, Build contract, Production caller chain, Cross-repo seams) | spec-standard plan check |
| Tasks | `task-planner` | `tasks.md`: `- [ ] T001 [P] [US1] <ROW-ID> ...` | spec-standard task-line check |
| Analyze | `spec-verifier` | `checklists/requirements.md`, gap fixes | spec-standard analysis and checklist |
| Implement | `feature-development-pipeline` | code and bound tests (`mark.spec("ID")` or `// spec: ID`) | `pipelines-hook spec-trailers` |
| Land | repository development skill | commit with `Spec: <IDs>` directly above `Co-Authored-By` | `spec-status` computes SPECIFIED, LANDED, VERIFIED, RETIRED |
| Release | repository development skill | pipelines `releases/*.yml` bundles (PIPE-RELEASE-R020 to R024) | `release-standard` |

Never write code for a row that is not SPECIFIED in this repository's `specs/`. If no row owns the behavior, extend the owning spec first. Never write `status.json` or a `Status:` line; the state is computed.

> Claude Code loads this file via `CLAUDE.md` (`@AGENTS.md` import) — the two stay in sync. Edit this file, not `CLAUDE.md`.


> **Notice:** This project uses **Spec-Driven Development (SDD)**.
> - Project constitution and governance: `.specify/memory/constitution.md`.
> - Feature specifications and tasks: `specs/terminal-runtime/`.
> This file (`AGENTS.md`) is for system-prompt context; the `specs/` tree is the source of truth for architecture and new features.

<!-- Ecosystem Concepts (cross-project, from agent-utilities kernel) -->
<!-- CONCEPT:AU-OS.deployment.infra-orchestration Ecosystem Topology Map — classified as FrontendPackage -->
<!-- CONCEPT:AU-KG.memory.background-learning-engine Cross-Session Chat Recall — consumed via kernel API -->
<!-- CONCEPT:AU-KG.memory.ground-truth-preamble-declaring Project-Aware Context — AGENTS.md auto-loaded by kernel -->
<!-- CONCEPT:AU-KG.temporal.bi-temporal-memory-layers Cross-Pillar Synergy Engine — topology consumer -->
<!-- CONCEPT:AU-ECO.toolkit.journey-map-milestones Terminal Agent Launcher — --prompt CLI flag for tmux-spawned one-shot execution -->
- This is a production-grade Rust/Ratatui application distributed through PyPI.
- Shortcuts are not appropriate. When in doubt, you must work with the user for guidance.
- Any documentation you write, including in the README.md, should be clear, concise, and accurate like the official documentation of other production-grade native applications.
- Make sure any comments in code are necessary. A necessary comment captures intent that cannot be encoded in names, types, or structure. Comments should be reserved for the "why", only used to record rationale, trade-offs, links to specs/papers, or non-obvious domain insights. They should add signal that code cannot.
- The current code in the package should be treated as an example of high quality code. Make sure to follow its style and tackle issues in similar ways where appropriate.
- Anything is possible. Do not blame external factors after something doesn't work on the first try. Instead, investigate and test assumptions through debugging through first principles.

## Boundaries

- **Owns:** what a person sees in the terminal.
- **Never builds:** data access other than through arbora, or a decision (route decisions to epistemic-graph). Served operations go to arbora.
- **Allowed integration:** public Arbora wire contracts. No EG or Arbora internals run in-process.

Route every feature with the [ecosystem boundaries standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ecosystem-boundaries.md) before any code. A part this repository does not own goes to its owner's specs.

# Native Development Instructions

`tuig` is the only runtime executable and Rust/Ratatui is the only frontend.
Python is developer tooling only. Do not restore Textual or a compatibility CLI.
Use the existing native Arbora client and keep authorization upstream.

## CLI

Use `tuig --help` for supported invocation. `--headless` supports native unary
prompt execution or observation without a terminal. Missing native composition,
streaming and approval support remain explicit requirements, not Python fallbacks.

## Detailed Documentation

Operator documentation lives in `docs/`. See [architecture](docs/architecture.md),
[native features](docs/features.md), [configuration](docs/configuration.md),
[retained gaps](docs/status.md) and [development](docs/development.md).

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

The repository root must contain only canonical project files. Tracked root entries and their purposes are declared in `.config/repo-layout.toml`.
Only `.specify/memory/constitution.md` may remain tracked under `.specify/`.
Canonical specifications live in `specs/`; historical source records live in `plans/`. NEVER write scratch/debug/migration files to the repo —
especially the root: no `fix_*.py`/`migrate_*.py`/`refactor_*.py`/root `test_*.py`,
no `*.db`/`*.log`/scratch `*.txt`/`*.orig`/`*.rej`/`*.bak`, no build artifacts
(`*.tsbuildinfo`), and no SI scratch dirs (`.agent/`, `.agents/`, `.agent_data/`,
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

## Approved Source-Only Merge Policy

For small source-only repairs, the user-approved source-merge policy permits
merge with focused regression coverage, normal lint/type/security checks, and
no new failures versus the same current-main revision in the same environment.
Record the baseline revision, commands, existing failures, and deferred gates
in the PR. This is an explicit exception to the fully-green prerequisite above;
do not suppress checks or report deferred checks as passing. Release gates and
full native qualification for native changes remain required. The all-files
pre-commit gate still runs; publication through the GitHub API does not run the
local pre-push release checks, which must be disclosed in the PR receipt.

## Working with Git Worktrees (multi-session)

Multiple agents/sessions work the `agent-packages/*` repos concurrently. **Do not
edit the canonical checkout** (`${AGENT_PACKAGES_ROOT}/<repo>`) — a
background `repository-manager` sync can reset its working tree and discard
uncommitted edits. Take your own git worktree on your own branch instead:

```bash
# preferred — repository-manager MCP:
rm_worktree add <repo> <your-branch>      # -> ${XDG_STATE_HOME}/repository-worktrees/<repo>/<your-branch>

# raw-git fallback:
git -C agent-packages/<repo> checkout main
git -C agent-packages/<repo> worktree add ${XDG_STATE_HOME}/repository-worktrees/<repo>/<branch> -b <branch>
```

Work in the worktree and **commit often** (commits survive a working-tree reset).
Each session must use a **distinct branch** — git allows a branch in only one
worktree, which is what keeps concurrent sessions from colliding. Worktrees live
under `${XDG_STATE_HOME}/repository-worktrees/` (outside the workspace scan, so the sync leaves them
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

## Commands

```bash
uv run --frozen --no-install-project --group test pytest tests -q
cargo test --locked --manifest-path native/tuig/Cargo.toml
tuig                                     # run the terminal app
uvx --from pre-commit==4.6.0 pre-commit run --files $(git diff --name-only origin/main...HEAD)
```

## Quality gates

`.pre-commit-config.yaml` runs ruff, mypy, vulture, codespell, the `spec` and `secrets` hooks and `pytest`. A change must pass them before it lands. A gate must not be bypassed with a skip, a `type: ignore` comment or an allowlist entry.

## Branching & isolation

Work in a real `git worktree add` from `origin/main`. The canonical checkout must stay untouched. Stage explicit paths only, and never run `git stash`.

## Documentation

Docs live in `docs/` and publish through `mkdocs.yml`. Pages must stay short and factual.

## Specs: extend first

Find the spec row that owns the behavior before any code change. Search with `git grep -n "<term>" -- specs`. Cite the row ID in the commit `Spec:` trailer. Extend the owning spec before any new spec text. Add a child row, a new rollup, or a dated `plan.md` "Amendments" entry. Create a new spec only for a capability that no spec owns. Audits, reviews, and carry-overs land in the owning spec. They never get a spec directory. Reuse an existing function, module, or store before adding one. The rules are the ecosystem [spec standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/spec-standard.md).
