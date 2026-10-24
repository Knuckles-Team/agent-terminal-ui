# Configuration Reference

Settings are managed by `settings.py`. The tables below describe the Python entry point unless marked as native.

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

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_URL` | `http://localhost:8000` | Arbora base URL for A2A chat and REST operations. |
| `AGENT_BEARER_TOKEN` | unset | Caller credential for Arbora; required for remote endpoints. |
| `AGENT_AUTH_MODE` | `bearer` | Native terminal only. Explicit `none` permits anonymous task operations against loopback Arbora configured for no authentication. Unset the bearer token in this mode. |
| `AGENT_THEME` | `tokyo-night` | Startup theme for Python and native. Unknown names fall back to `tokyo-night`. |
| `TEXTUAL_ANIMATIONS` | `full` | Set to `none` to disable entrance animations (reduced motion). |
| `AGENT_UTILITIES_DATA_DIR` | platform default | Override the local session data directory. Takes precedence over the configuration-relative fallback. |
| `AGENT_UTILITIES_CONFIG_DIR` | platform default | Override the settings directory. Without a data override, local session data uses its sibling `share/agent-utilities` directory. |
| `AGENT_LOG_FILE` | ignored | Never opened by the main screen or native terminal. Log views require an authenticated host reader. |
| `AGENT_TASK_ID` | unset | Native only. Read an existing task; does not resume chat. Reject empty, control-containing or over-512-byte identifiers. |
| `AGENT_SUBMISSION_TIMEOUT_SECONDS` | `300` | Native only. Decimal seconds from 1 to 900; invalid values fail startup. No automatic resubmission. |
| `AGENT_INCLUDE_COMMITTED_EVENT` | `false` | Native only. Accept exactly `true` or `false`; request committed-event evidence without granting access. |
| `NO_COLOR` | unset | Python follows Textual presence semantics. Native disables theme colors only for a nonempty value. |
| `TERM_PROGRAM` | empty | Python notification detection uses the terminal application name to choose OSC9 or fallback behavior. |
| `TERM` | empty | Python notification detection recognizes xterm, screen and tmux families for BEL fallback. |
| `SHELL` | `/bin/bash` | Python shell sessions use this executable unless an explicit shell path is set. |

The `/op` command needs Python 3.12 or newer and the Arbora distribution
containing the generated client. Without it, `/op` refuses with
`CLIENT_UNAVAILABLE`; basic A2A chat remains available. The package requires Python 3.12 or newer.

## Theme and log entry points

Python startup accepts the registered Textual themes.
Native themes: `tokyo-night`, `nord`, `gruvbox`, `textual-light`.
Both use `tokyo-night` when AGENT_THEME is unset or unknown.
Alt+Shift+T cycles Python themes; F6 cycles native themes.
NO_COLOR disables Python colors when present, including an empty value.
Native colors are disabled only when NO_COLOR is nonempty.

AGENT_LOG_FILE does not grant filesystem access in either terminal.
Python `/logs` and Ctrl+V require an authenticated host reader.
Native `l` opens the host-log view and also requires authenticated host access.
Without that access, both display refusal and never open the given local path.
No-color mode does not change this access rule.

## Dynamic setting overrides

`AppSettings.get(key)` checks the exact key, then its uppercase spelling, before stored configuration.
A nonempty lowercase value wins over uppercase. An empty lowercase value falls through to uppercase.
An empty uppercase value is still an override. Other mixed-case spellings are not searched.
Boolean values accept `true`, `1`, `yes` and `on`, without case sensitivity; every other value becomes false.
Integer values use Python integer parsing. Invalid integers remain strings; environment choices are not validated against schema choices.
String environment overrides remain literal. Stored strings expand `$NAME` and `${NAME}` unless the caller disables expansion.
Unknown referenced variables remain unchanged. Arbitrary requested keys also support exact-key and uppercase lookup and return raw strings.

These are the current schema keys and their uppercase aliases. This lists lookup support, not proof that every setting changes runtime behavior.

| Setting key | Uppercase alias |
|---|---|
| `theme` | `THEME` |
| `tool_expand` | `TOOL_EXPAND` |
| `diff_view` | `DIFF_VIEW` |
| `sidebar_visible` | `SIDEBAR_VISIBLE` |
| `shell_command` | `SHELL_COMMAND` |
| `agent_url` | `AGENT_URL` |
| `default_mode` | `DEFAULT_MODE` |
| `show_tokens` | `SHOW_TOKENS` |
| `auto_scroll` | `AUTO_SCROLL` |
| `approval_policy` | `APPROVAL_POLICY` |
| `sandbox_mode` | `SANDBOX_MODE` |
| `auto_allow` | `AUTO_ALLOW` |
| `auto_compact` | `AUTO_COMPACT` |
| `reasoning_effort` | `REASONING_EFFORT` |
| `auto_model_routing` | `AUTO_MODEL_ROUTING` |
| `notification_method` | `NOTIFICATION_METHOD` |
| `notification_threshold_secs` | `NOTIFICATION_THRESHOLD_SECS` |
| `snapshots_enabled` | `SNAPSHOTS_ENABLED` |
| `snapshots_max_age_days` | `SNAPSHOTS_MAX_AGE_DAYS` |
| `hooks_enabled` | `HOOKS_ENABLED` |
| `trust_mode` | `TRUST_MODE` |
| `max_concurrent_tasks` | `MAX_CONCURRENT_TASKS` |
| `max_conversation_widgets` | `MAX_CONVERSATION_WIDGETS` |
| `max_log_lines` | `MAX_LOG_LINES` |

Environment lookup precedes local `settings.toml`, global `config.json` and schema defaults, in that order.
The transport factory reads `AGENT_URL` directly. A lowercase `agent_url` setting does not override that factory.
Startup theme selection reads `AGENT_THEME`; `theme` and `THEME` are settings lookups, not startup aliases.

Shells and lifecycle hooks inherit the process environment. Their additional context variables belong to those subprocess interfaces.
The terminal does not interpret every inherited variable. HTTP proxy, locale and framework settings remain dependency-level inputs.
`TEXTUAL_ANIMATIONS` and `NO_COLOR` are included here because the terminal explicitly documents their presentation effects.

## CLI Flags

Run `agent-terminal-ui --help` for the complete Python argument list.

| Flag | Purpose |
|------|---------|
| `--help` | Print usage and exit without starting a client. |
| `--prompt TEXT` | Send an initial prompt. Interactive mode submits it after startup. |
| `--override` | Set the interactive auto-approval preference. This does not grant backend authority. |
| `--bg` | Start the interactive Agent View. |
| `--headless` | Run `--prompt` without the widget tree. Requires a nonempty prompt. |
| `--model ID` | Compatibility option. The A2A transport ignores it; the server selects the authorized model. |
| `--session ID` | Reuse a context ID. This does not load prior turns for the model or provide durable conversation resume. |
| `--mode {ask,plan,build}` | Select the typed task for a headless turn. Defaults to `ask`; interactive startup does not consume it. |
| `--observe-task ID` | Read an existing task without submission or approval. |

Observation accepts a nonblank ID of at most 512 characters. It cannot combine
with `--prompt`, `--override`, `--bg`, `--model`, `--session`, or a non-default
`--mode`. It can combine with `--headless`. `--override` and `--bg` have no effect
in headless mode. Neither client mode grants permission to execute tools.

```bash
agent-terminal-ui --headless --prompt "summarize the task" --mode ask
agent-terminal-ui --observe-task TASK_ID
agent-terminal-ui --headless --prompt "new turn" --session CONTEXT_ID
```

The last example reuses a context identifier only. Full history loading and
successful governed model selection remain separate acceptance requirements.

## Theme and accessibility contract

Python uses Textual's `primary`, `secondary`, `accent`, `warning`, `error`,
`success`, `foreground`, `background`, `surface` and `panel` tokens. Tokyo Night
is the default. Tokyo Night, Nord, Gruvbox and Textual Light are the shared
baseline palettes. Their foreground/background contrast must be at least 4.5:1.
This floor does not assert contrast for every accent or widget combination.

Set `NO_COLOR` before launch for Textual's monochrome output. Python follows
Textual's presence rule, including an empty value. Native mode currently uses
nonempty `NO_COLOR` to select terminal foreground/background colors. Labels and
keyboard help remain necessary; color alone must not convey task state. Full
cross-client theme and performance parity remains pending.

The native terminal cycles its four baseline palettes with F6: Tokyo Night,
Nord, Gruvbox and Textual Light. Switching works in the task, inspector, log
and cancellation views without restarting or changing requests. Nonempty
`NO_COLOR` keeps terminal foreground and background colors after switching.

Native anonymous mode sends no Authorization header and never falls back from
failed authentication. It permits ordinary task submission, reads, observation
and cancellation, not authenticated host-log receipts.
The client accepts only localhost, 127.0.0.1 and [::1] endpoints. It pins
localhost to 127.0.0.1 and disables proxy routing. Remote connections retain the
existing HTTPS and bearer requirements.
