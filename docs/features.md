# Features

## Slash commands

Commands are registered in `commands.py` (`CommandProcessor.commands`) and surfaced
through the input overlay: type `/` to open a fuzzy-filtered menu (ESC to close,
TAB to cycle, Enter to run). Aliases are collapsed in the menu, so `/exit` and its
alias `/quit` appear once.

The registry groups commands by area:

| Area | Commands |
|------|----------|
| Core | `/help`, `/clear`, `/exit` (alias `/quit`), `/config`, `/keybindings` |
| Modes | `/plan`, `/chat`, `/build` |
| Conversation | `/compact`, `/context`, `/recap`, `/export`, `/diff`, `/focus`, `/fast`, `/image` |
| Models & cost | `/model`, `/stats` (alias `/cost`) |
| Theme | `/theme` |
| Queue | `/queue`, `/queue:clear`, `/queue:toggle` |
| Goals (autonomous) | `/goal`, `/goal:status`, `/goal:cancel`, `/goal:history` |
| Sessions & agents | `/agents`, `/attach`, `/bg`, `/history` |
| Knowledge graph | `/graph`, `/kb`, `/impact`, `/codemap`, `/search` |
| Engine surface | `/ask`, `/nl`, `/obs`, `/broker`, `/kvcache` |
| Capabilities & runs | `/capabilities`, `/capability`, `/run` (alias `/runs`) |
| Project & SDD | `/init`, `/sdd`, `/memory`, `/add-dir`, `/prompts`, `/review`, `/test`, `/simplify` |
| MCP & tools | `/mcp`, `/mcp:reload`, `/tools`, `/skills`, `/resources` |
| Ops | `/logs`, `/cron`, `/pipeline`, `/maintenance` |

### Engine-surface commands (`/graph/*` gateway routes)

These wrap the epistemic-graph engine surfaces exposed over the AU gateway
(action-routed `/graph/*` twins of the `graph_*` MCP tools). Each degrades cleanly
to an inline error when the engine build lacks that surface.

- `/ask <question>` — DB-GPT-style data-analyst loop (`POST /graph/ask-data`,
  KG-2.308): schema-link → plan → execute → self-correct → synthesized answer.
- `/nl <question>` — NL→query planned by the AU fleet LLM (`POST /graph/nl-query`,
  KG-2.305); shows the generated query plus rows. Prefix `preview ` to dry-run the
  query without executing it.
- `/obs <promql>` — PromQL instant query (`POST /graph/promql`, KG-2.310);
  `/obs range <promql>` runs a range query over the last 15m and renders a Unicode
  sparkline; `/obs traces [service]` searches distributed traces (`POST /graph/traces`).
- `/broker [stats|queues|exchanges]` — engine message-broker status
  (`POST /graph/broker`, KG-2.310).
- `/kvcache` — shared content-addressed KV-cache occupancy and dedup counters
  (`POST /graph/kvcache`, KG-2.306).

Some commands depend on optional backend endpoints and degrade or report an error
when the backend does not expose them — see [Known Issues](agents.md#known-issues).

### Live capabilities and run replay

Alt+C, `/capabilities [query]`, the global Textual command palette, and the
Capabilities sidebar tab all open the same live gateway catalog. Selecting a
capability fetches its detail descriptor and generates top-level inputs from the
selected action's JSON Schema. The UI shows runtime availability, missing
preconditions, legacy route metadata, renderer hint, and policy metadata instead
of assuming that every catalog entry can execute. `available` with `readiness=cold` remains
callable and is labeled as a first-call warm-up, not as degraded.

The palette labels each action's legacy REST metadata as non-frontend-executable
and never constructs that route. Every execution goes through
`POST /api/capabilities/{capability_id}/invoke`, where the gateway owns action
routing, identity, policy, audit, and canonical run creation.
The normal HTTP 202 response is a `running` acknowledgement, not a completed
result; eventual output is read from the run's `tool_result` event.

Sensitive tool results stay redacted in replay. The inspector displays only the
gateway event metadata and never calls a reveal/claim route, caches a revealed
value, or copies one automatically. A future reveal-once control must be an
explicit, owner-scoped action with no-store handling; until that contract is
implemented end to end, the Terminal UI reports the redacted event as-is.

Preflight is non-executing. The palette reruns it immediately before invocation,
blocks invalid, denied, queued, unavailable, and degraded actions, and requires a
separate operator confirmation for allowed mutating actions. Unknown side effects
fail closed through gateway policy. The gateway remains authoritative and rechecks
identity and policy at execution.

If the acknowledgement is HTTP 202 `approval_required`, the palette keeps the exact
request and server-bound approval, run, and session IDs. An explicit approve
action grants the approval and resumes that same request with those IDs; denial
does not execute it.

`/run [run_id]` opens live Mission Control for the canonical event stream. With
no explicit or recently observed run ID, it opens a newest-first browser backed
by `GET /api/runs`, scoped to the current session when available. Mission Control
polls cursor replay from `GET /api/runs/{run_id}/events`, drains retained pages,
deduplicates by sequence, and follows until an exact terminal event arrives.
Only `run_completed`, `run_failed`, `run_interrupted`, `run_cancelled`, and
`error` are terminal. `graph_complete` and `final_output` remain progress because
final output and the authoritative run completion can follow graph completion.
The view reports unknown, expired, empty, degraded, and truncated process-local
history explicitly, including the missing sequence range when the bounded replay
window forces a reset.

Session IDs remain stable across turns while each execution receives a distinct
run ID; the palette and replay browser preserve both identities independently.

Machine-readable native/generated support is recorded in
[`capability-coverage.json`](capability-coverage.json).

### `/model`

Backed by the `agent-utilities` multi-model registry (`GET /models`):

- `/model` or `/model list` — render the configured models in a table (id, name,
  provider, tier, tags, default marker, per-1M cost).
- `/model show` — show full metadata for the active model (falls back to the
  registry default when no override is set).
- `/model set <id>` — pick a model id for subsequent turns. The id is stored on the
  app and propagated by `AgentClient` as an `x-agent-model-id` header so the backend
  can override the registry default for the session.

Zero-cost / local models render as `$0.00 / $0.00` rather than `-`.

### `/goal`

Starts an autonomous goal loop. The objective string is parsed locally by the
dependency-free `goal.py` parser — `/goal <objective> until <end_state> without
<constraints>` — and submitted to the backend. See [Goal Command](goal_command.md).

## Keyboard shortcuts

Application bindings (`app.py::BINDINGS`):

| Binding | Action |
|---|---|
| `Ctrl+C` | Interrupt the current operation |
| `Ctrl+D` | Exit session (with confirmation) |
| `Ctrl+A` | Select all |
| `Ctrl+Q` | Quit |
| `Ctrl+H` | Show help |
| `Ctrl+U` / `Ctrl+Y` | Clear / restore input |
| `Ctrl+G` | Open input in `$EDITOR` |
| `Ctrl+R` | Reverse history search |
| `Alt+P` | Model picker |
| `Alt+T` | Toggle extended thinking |
| `Alt+O` | Toggle fast mode |
| `Alt+D` | Service dashboard |
| `Alt+C` | Live capability palette |
| `Shift+Tab` | Cycle reasoning effort / mode |
| `Esc Esc` | Rewind (experimental) |

Main-screen bindings (`screens/main.py::BINDINGS`):

| Binding | Action |
|---|---|
| `Ctrl+B` | Toggle workflow sidebar |
| `Ctrl+L` | Clear conversation |
| `Ctrl+V` | Toggle server-log panel |

## Input prefixes

- `!` — run the rest of the line as a shell command (e.g. `!ls -la`).
- `@` — fuzzy file-mention autocomplete (e.g. `@app.py`), via the file
  suggestions overlay.

## Headless mode

Run a single prompt without the TUI, streaming output to stdout:

```bash
agent-terminal-ui --headless --prompt "summarize the open PRs"
agent-terminal-ui --headless --prompt "run the tests" --model claude-opus-4-8
```

No Textual widget tree is loaded, so a headless instance is lightweight (~30MB) —
suited to running many concurrent, non-interactive sessions against one shared
backend. See [Architecture](architecture.md#run-modes).

## Conversation UI

- Structured message blocks: user messages, agent responses (streaming Markdown),
  and expandable tool-call blocks with status-colored borders.
- New blocks fade in on mount (`tui/animation.py`); motion is disabled
  automatically under `TEXTUAL_ANIMATIONS=none` / reduced-motion environments.
- The conversation prunes to `max_conversation_widgets` (default 50) to bound
  memory; full history is persisted in SQLite (see
  [Session Management](session_management.md)).
- Themes: default `tokyo-night`; switch live with `/theme <name>` across Textual's
  built-in themes, or set the startup theme via `AGENT_THEME`.
