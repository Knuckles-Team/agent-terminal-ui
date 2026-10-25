# Features

## Slash commands

Commands are registered in `commands.py` (`CommandProcessor.commands`) and surfaced
through the input overlay: type `/` to open a fuzzy-filtered menu (ESC to close,
TAB to cycle, Enter to run). Aliases are collapsed in the menu, so `/exit` and its
alias `/quit` appear once.

The registry groups commands by area, including aliases and `:`-suffixed
subcommands:

| Area | Commands |
|------|----------|
| Core | `/help`, `/clear`, `/exit` (alias `/quit`), `/config`, `/keybindings` |
| Conversation | `/compact`, `/context`, `/recap`, `/export`, `/diff`, `/focus`, `/fast`, `/image`, `/file` |
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

Ordinary requests need no ask, plan or build mode. Enter the request directly;
Arbora owns request handling. Required approvals remain separate.

### Unavailable session and fast-mode actions

`/bg`, `/attach` and `/fast` report unavailable until Arbora serves their
contracts. They do not change session state, resume a conversation or select
a model. Alt+O reports the same fast-mode refusal.

### Inline text files

`/file PATH` stages a local UTF-8 text file for the next prompt. Quote paths with
spaces. `/file` lists staged names; `/file --clear` removes the staged files.
Staging makes no request. The next prompt sends each file as inline `text/plain`.
Files retain their base names and bytes. The limit is eight files and 65,536
total bytes. Empty, invalid UTF-8, oversized and non-regular files are refused.
The command does not expand shell expressions or fetch URLs.
The final path component cannot be a symbolic link.
`/clear` and interruption remove staged files. A client or conversation change
refuses a staged or queued file turn. The server may enforce a lower upload limit.
Images and pasted images remain unsupported; `/image` still reports refusal.

### Read-only task history

`/history` lists caller-owned Arbora tasks. Press Enter to read a selected
reply or N for the next server page. R refreshes from the first page; Esc closes
the view. Refresh clears old rows and replies before reading fresh task states. Browsing does not change
the active conversation or submit work. Missing replies show unavailable.
This view does not yet provide prior user turns, ordered conversation
summaries or conversation resume.

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

`/run <run_id>` and `/runs <run_id>` inspect one authorized run through
`runs.get` and `runs.events`. The overview shows the server's task identity and
status. Applied configuration, context budget, cost and terminal reason stay
unavailable until the public read provides a supported projection.
`/run plan <run_id>` remains a separate current-plan view.

The inspector reuses the bounded public-event parser. It shows only public
summaries and allowlisted execution facts, not opaque producer payloads. R
replays from the start, F pauses or resumes follow, and Esc closes the view.
The public `arbora-run-events-v1` contract marks `graph_complete`, `error` and
`run_cancelled` as terminal; legacy event names do not establish completion.
The view retains at most 1000 events and 128 KiB of displayed text. It reports
omitted earlier events. Invalid cursors and duplicate events refuse the read,
not a guessed reset. Refusal, refresh and connection changes clear old content.

Arbora does not expose a run-list operation, so run discovery is unavailable.
Provide an explicit run ID. An unknown operation, incompatible registry or denied read
stays unavailable, with no legacy REST fallback. This current-main contract
integration does not establish support in an older released Arbora package.

### Flat execution graph (Python)

`/run graph <run_id> [task_id]` reads the separate `runs.execution_graph` operation.
Provide an explicit run ID, and optionally its root task ID. Arbora resolves an omitted root.
The screen shows each plan step once and lists `depends_on` edges from predecessor to dependent.
Use Up/Down to select a step, Tab to reach the scrollable details, R to refresh and Escape to close.
Selection does not change the chat target or draft.

Topology is complete within the declared plan. Lifecycle data is an incomplete observed prefix.
The view shows its cursor and whether more events exist. `unobserved` does not mean pending or complete.
Plan steps are not child agents. Transcripts, child messages and continuation are unavailable.
Refresh clears old details before reading. Denial or a changed connection/context clears the view.
Unsupported installed clients fail closed without a legacy request.

The companion native inspector source adds graph mode through `i`, then `g`.
Its Rust tests, Clippy and compiled-terminal checks remain unrun for this candidate.
Python mounted tests do not establish native parity or released producer support.
Nested agents, public records and served end-to-end qualification remain open.
This slice does not change the existing `/run` event inspector or `/run plan`.

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
| `Alt+O` | Report unavailable fast-mode selection |
| `Alt+D` | Service dashboard |
| `Alt+C` | Live capability palette |
| `Esc Esc` | Rewind (experimental) |

Main-screen bindings (`screens/main.py::BINDINGS`):

| Binding | Action |
|---|---|
| `F8` | Switch focus between conversation and composer |
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
  built-in themes, cycle them with `Alt+Shift+T`, or set the startup theme via
  `AGENT_THEME`.

### Public run details

A task with a server-provided task, context and run binding has two inline
sections: Public model summary and Execution trace. Both start collapsed.
Focus a header and press Enter or Space, or click it, to expand. The first
expansion reads the authorized runs.events operation. Missing producer support
or denied reads show unavailable; the client does not invent a summary.

Python preserves each fold during updates and replay. Press r while a detail
header has focus to reload. Native uses Tab to select a detail header,
Enter or Space to toggle it, and Escape to leave that selection. Its r key
keeps the existing task refresh and also reloads public details. Public summaries
and execution facts stay separate from the answer and from private reasoning.
Tool output uses the tool_expand setting until an explicit user toggle.

Public details retain at most 1,000 records and 128 KiB of display text.
The view may omit older records. Refresh replays the authorized history without
changing the selected fold states. Older backends without a run binding display an
unavailable placeholder and do not cause a guessed run read.

Mission Control remains on the legacy replay schema. It explicitly refuses the new
public projection; use these inline sections for that projection.
