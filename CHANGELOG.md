# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Headless mode** — `--headless` (with `--prompt`, optional `--model`) runs a single agent turn over `AgentClient` with no Textual widget tree, streaming events to stdout. New `headless.py` (`HeadlessRunner`, `StreamSink`, `RenderSink` protocol); the Textual app is imported lazily so headless instances stay ~30MB. Added `AgentClient.aclose()`.
- **Slim Dockerfile** — runtime-only `python:3.13-slim` image shipping the frontend without test/shell extras or `agent_utilities`; point it at a shared backend via `AGENT_URL`.
- **Conversation polish & motion** — visual hierarchy for user/agent/tool message blocks, a status-mode badge, input focus accents, and a shared `tui/animation.py` `animate_in()` entrance fade (honors `TEXTUAL_ANIMATIONS` / reduced motion).
- **Test harness** — `pytest-textual-snapshot` golden snapshots across themes, a full slash-command + key-binding coverage matrix, and an import-guard test asserting the frontend never imports `agent_utilities`/`torch`.
- **Override Mode (CONCEPT:ECO-4.5)** — `--override` CLI flag enables auto-approval of all tool calls (yolo mode), bypassing the `ToolApprovalScreen` modal for high-trust automation scenarios. When active, pending tool calls are immediately accepted without user interaction.
- **Initial Prompt Injection** — `--prompt` CLI flag to pass an initial task directly on launch. The prompt is auto-submitted via an `on_mount` startup hook once the TUI is ready, enabling one-shot headless execution.
- **GitHub Pages Workflow** — Added `.github/workflows/pages.yml` for automated documentation deployment on push to `main`.
- **Pytest Markers and Warnings** — Added `integration` marker and `RuntimeWarning` filter to `pytest.ini` for cleaner test output.
- **Ecosystem Integration (CONCEPT:ECO-4.7)** — Classified as `FrontendPackage` in the kernel ecosystem topology. Inherits cross-session chat recall (KG-2.13) and project-aware context (KG-2.14) from `agent-utilities` kernel.
- **TUI-1:** SQLite-backed session persistence with crash recovery, checkpoints, session fork/resume, and durable offline queue at `~/.config/agent-terminal-ui/agent_terminal_ui.db`
- **TUI-2:** Side-git workspace snapshots for pre/post-turn rollback with `/restore N`, diff viewer, and auto-pruning
- **TUI-3:** Three-tier reasoning effort system (OFF/HIGH/MAX) with `Shift+Tab` cycling and auto model routing via complexity heuristics
- **TUI-4:** Multi-tier context compaction engine (L1/L2/L3/Cycle) with configurable token thresholds and auto-compact toggle
- **TUI-5:** Durable task queue with SQLite persistence, bounded concurrency, timeline events, checklist state, and crash recovery
- **TUI-6:** Lifecycle hooks system with TOML configuration, timeout-protected shell execution, conditional triggers, and `shell_env` injection
- **TUI-7:** Desktop notifications via OSC 9/BEL with terminal auto-detection and configurable time threshold
- **TUI-8:** Workspace boundary enforcement with three sandbox modes (read-only, workspace-write, danger-full-access), trust mode, and allow/deny lists
- **TUI-9:** Multi-entry draft stash system with `Ctrl+S` stash, `/stash list`, and `/stash pop`
- **TUI-10:** Enhanced per-turn cost tracking with cache hit/miss breakdown, configurable pricing registry, and session-level aggregation by model
- **TUI-11:** Approval policy engine with three policies (on-request/auto/never), auto-allow prefix lists, and mode-aware strictness
- **TUI-12:** Job Center for shell process management with output tailing, linked tasks, and job lifecycle tracking
- Added 14 new settings to `settings.py` for all new features
- Added new slash commands: `/restore`, `/sessions`, `/trust`, `/sandbox`, `/approve`, `/jobs`, `/tasks`, `/stash`, `/hooks`
- Added `Shift+Tab` and `Ctrl+S` keyboard shortcuts

### Changed
- **Lightweight frontend** — `/goal` now uses a vendored, dependency-free `goal.py` parser instead of importing the backend `GoalSpec`; the Alt+D service dashboard fetches over HTTP (`GET /api/dashboard/full`) instead of constructing the gateway aggregator in-process. The frontend now imports zero `agent_utilities` on any path.
- `AgentApp` accepts an injectable `client` for testing.
- Documentation refreshed: architecture diagram, accurate command/keybinding reference, environment-variable and CLI-flag tables, and the corrected session-store path (`~/.local/share/agent-utilities/agent_terminal_ui.db`).
- Extended `danger.py` with `ApprovalPolicy` enum and `ApprovalEngine` class
- Extended `shell.py` with `JobRecord` and `JobCenter` classes

### Fixed
- Slash-command menu no longer shows `/exit` twice — aliases (e.g. `quit`) are collapsed to a single entry.

## [0.2.0] - 2026-04-30

### Added
- Initial release
