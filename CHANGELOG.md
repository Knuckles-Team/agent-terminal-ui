# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
- Extended `danger.py` with `ApprovalPolicy` enum and `ApprovalEngine` class
- Extended `shell.py` with `JobRecord` and `JobCenter` classes

### Fixed
-

## [0.2.0] - 2026-04-30

### Added
- Initial release
