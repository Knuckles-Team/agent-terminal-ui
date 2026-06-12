# Session Management

`agent-terminal-ui` keeps conversations durable across restarts and crashes. State
lives in SQLite, and the workspace can be rolled back to any prior turn via
side-git snapshots.

## Durable sessions (TUI-1)

Sessions, turns, checkpoints, and the offline queue are stored in a SQLite
database managed by `session_manager.py` (`SessionManager`).

- **Location:** `~/.local/share/agent-utilities/agent_terminal_ui.db` (the XDG
  data directory). Override the parent directory with `AGENT_UTILITIES_DATA_DIR`.
- **Shared store:** the path is resolved from the shared `agent-utilities` data
  directory, so durable state is consistent across frontends on the same machine.

Key operations:

| Operation | Method | Notes |
|-----------|--------|-------|
| Create | `create_session(...)` | Opens a new durable session. |
| List / filter | `list_sessions(...)` | Browse via the `/history` picker. |
| Fork / resume | `fork_session(session_id, turn)` | Branch a session at any turn number. |
| Archive | `archive_session(session_id)` | Archive without deleting history. |

- **Pre-turn checkpointing:** a checkpoint is written before each turn so an
  interrupted turn can be recovered on restart.
- **Offline queue:** messages submitted while disconnected are queued durably and
  replayed when the backend is reachable again.

## Workspace snapshots & rollback (TUI-2)

`workspace_snapshots.py` (`WorkspaceSnapshotManager`) captures pre/post-turn
snapshots of the working tree in a side git repository — it never touches your
project's own `.git`.

- **Restore:** `/restore N` rolls the workspace back to the snapshot at turn `N`
  (`restore(turn_number, phase="pre")`).
- **Diff:** view changes between snapshot points from the diff viewer.
- **Auto-prune:** snapshots older than `snapshots_max_age_days` (default 7) are
  cleaned up. Disable the whole feature with `snapshots_enabled = false`.

See [Configuration](configuration.md) for the related settings
(`snapshots_enabled`, `snapshots_max_age_days`).

## Related

- [Agent View](agent_view.md) — managing multiple concurrent sessions.
- [Goal Command](goal_command.md) — autonomous goals checkpoint their state for
  crash recovery using the same durable store.
