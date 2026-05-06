# Configuration Reference

All configuration is managed via `settings.py` and stored in the settings store. New settings introduced in the DeepSeek-TUI parity update.

## Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `agent_url` | string | `http://localhost:8000` | Agent server URL |
| `default_mode` | choices | `ask` | Default interaction mode |
| `show_tokens` | boolean | `true` | Display token count in status bar |
| `auto_scroll` | boolean | `true` | Auto-scroll on new messages |
| `approval_policy` | choices | `on-request` | Tool approval policy (on-request/auto/never) |
| `sandbox_mode` | choices | `workspace-write` | File operation boundary |
| `auto_allow` | string | `""` | Comma-separated auto-approve command prefixes |
| `auto_compact` | boolean | `false` | Enable auto context compaction |
| `reasoning_effort` | choices | `high` | Default reasoning tier (off/high/max) |
| `auto_model_routing` | boolean | `false` | Auto-select model per turn |
| `notification_method` | choices | `auto` | Notification method (auto/osc9/bel/off) |
| `notification_threshold_secs` | integer | `30` | Min turn duration for notification |
| `snapshots_enabled` | boolean | `true` | Enable workspace snapshots |
| `snapshots_max_age_days` | integer | `7` | Snapshot retention period |
| `hooks_enabled` | boolean | `true` | Enable lifecycle hooks |
| `trust_mode` | boolean | `false` | Bypass approval for reads |
| `max_concurrent_tasks` | integer | `5` | Max background tasks |

## Sandbox Modes

- **read-only** -- All file write operations are blocked
- **workspace-write** (default) -- Writes allowed only within the workspace directory
- **danger-full-access** -- No filesystem restrictions (use with caution)

## Approval Policies

- **on-request** (default) -- Dangerous commands require user approval; safe commands pass automatically
- **auto** -- All tool calls are auto-approved (YOLO mode)
- **never** -- All tool execution is blocked

## Auto-Allow Prefixes

Configure command prefixes that bypass approval in on-request mode:

```
auto_allow = "cargo check, npm test, git status, pytest"
```

## Lifecycle Hooks

Hooks are configured in `~/.config/agent-terminal-ui/hooks.toml`:

```toml
[hooks]
enabled = true
default_timeout_secs = 15

[[hooks.hooks]]
name = "startup-check"
event = "session_start"
command = "echo 'Session started at $(date)'"

[[hooks.hooks]]
name = "post-edit-lint"
event = "tool_call_after"
command = "ruff check --fix ."
timeout_secs = 30
condition = { type = "tool_category", category = "file" }

[[hooks.hooks]]
name = "env-inject"
event = "shell_env"
command = "echo 'API_KEY=secret'"
```

### Supported Events

| Event | Trigger |
|-------|---------|
| `session_start` | When a new session begins |
| `session_end` | When a session is archived |
| `message_submit` | When the user submits a message |
| `tool_call_before` | Before a tool call executes |
| `tool_call_after` | After a tool call completes |
| `mode_change` | When the interaction mode changes |
| `on_error` | When an error occurs |
| `shell_env` | Collect environment variables for shell commands |

## Compaction Thresholds

Default token thresholds for context compaction:

| Tier | Threshold | Strategy |
|------|-----------|----------|
| L1 | 192,000 | Summarize old tool results |
| L2 | 384,000 | Summarize all turns outside verbatim window |
| L3 | 576,000 | Drop old turns, keep summary |
| Cycle | 768,000 | Hard reset with summary carry-forward |

The verbatim window preserves the last 16 turns in full fidelity.

## Cost Tracking

Built-in pricing registry (USD per million tokens):

| Model | Input | Output | Cached |
|-------|-------|--------|--------|
| default | $0.15 | $0.60 | $0.075 |
| flash | $0.07 | $0.30 | $0.035 |
| pro | $0.30 | $1.20 | $0.15 |
| gpt-4o | $2.50 | $10.00 | $1.25 |
| claude-sonnet | $3.00 | $15.00 | $1.50 |

Custom pricing can be set via `tracker.set_pricing(model, input, output, cached)`.
