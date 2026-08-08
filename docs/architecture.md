# Architecture

`agent-terminal-ui` is a thin, lightweight **frontend**. All heavy work — the
knowledge-graph engine, embeddings, model orchestration — lives in the shared
`agent-utilities` **backend**, which the client reaches over HTTP/SSE. The client
itself never imports `agent_utilities`, so a single instance stays in the tens of
MB and many can run against one backend.

## System overview

```mermaid
flowchart LR
    subgraph term["Terminal / tty"]
        UI["AgentApp (Textual TUI)<br/>interactive, ~60-85MB"]
    end
    subgraph head["Headless"]
        HL["HeadlessRunner + StreamSink<br/>no widget tree, ~30MB"]
    end

    UI -->|AgentClient| C
    HL -->|AgentClient| C
    C["AgentClient<br/>HTTP + SSE (httpx)"]

    subgraph backend["agent-utilities backend (shared, heavy)"]
        GW["Gateway / ACP + AG-UI<br/>/api/* , /acp/*"]
        KG["KG engine + embeddings<br/>(the ~1.5GB cost)"]
        DASH["/api/dashboard/*"]
        GW --- KG
        DASH --- KG
    end

    C -->|"stream() turns"| GW
    C -->|"/api/dashboard/full"| DASH
    C -->|"/api/enhanced/graph/*"| GW
    C -->|"/api/capabilities/*"| GW
    C -->|"/api/runs/*"| GW

    classDef heavy fill:#3a1f1f,stroke:#a44;
    classDef light fill:#1f2a3a,stroke:#48a;
    class KG heavy;
    class UI,HL,C light;
```

**Key boundary:** the frontend talks to the backend *only* through `AgentClient`.
A dedicated test (`tests/test_import_guard.py`) fails the build if importing the
app, the dashboard, the `/goal` parser, or the headless runner pulls in
`agent_utilities`, `torch`, or other heavy libraries.

## Run modes

| Mode | Entry | Footprint | Use |
|------|-------|-----------|-----|
| Interactive TUI | `agent-terminal-ui` | ~60-85 MB | a human at a terminal |
| Headless | `agent-terminal-ui --headless --prompt "…"` | ~30 MB | many concurrent non-interactive sessions |

The Textual application is imported **lazily** in `terminal_ui.py`, so a headless
run never loads the TUI widget tree. Headless rendering goes through a
`RenderSink` protocol (`headless.py`): the interactive `Conversation` widget and
the headless `StreamSink` present the same event vocabulary.

## Protocol connection

`agent-terminal-ui` consumes one normalized event vocabulary through
`AgentClient`, which is the only adapter this package ships. It speaks
**ACP** — this repo's own hand-rolled JSON-RPC (over HTTP) + SSE convention,
*not* an integration with Zed's `agent-client-protocol` SDK; there is no
dependency on that package and nothing here imports it. A future second
adapter (e.g. AG-UI) could implement the same normalized stream contract
without changing screen code, but no selector flag exists today because
there is only one adapter to select.

The workflow sidebar discovers graph nodes from sideband events at runtime — nodes
are never hardcoded. They appear as the graph emits `specialist_enter` /
`specialist_exit` events; phase labels (Planning, Discovery, Execution,
Validation) and completion markers derive from `routing_started`,
`routing_completed`, and `verification_result` events.

The backend uses **unified specialist discovery** (`discover_all_specialists()`)
to merge MCP agents and A2A peers into a single roster. Both emit the same
sideband events, so the TUI does not distinguish between them. The `tools-bound`
event includes `toolset_count`, `dev_tools`, and `mcp_tools` fields.

## Capability platform and run events

The capability UI consumes the gateway-owned schema 2.0 contract through
`AgentClient`: catalog search, detail, preflight, and governed invocation. Action
legacy REST routes are descriptive and `frontend_executable=false`; the frontend
executes exclusively through `execution.governed_invoke_route` at
`POST /api/capabilities/{capability_id}/invoke`. Lightweight dataclasses
in `capabilities.py` isolate widgets from raw payload drift without importing
`agent_utilities`. Textual's global command
palette, the Capabilities sidebar tab, and `/capabilities` converge on one
schema-generated form.

Availability and readiness are distinct. An `available` capability with
`readiness=cold` stays invocable and is rendered as a first-call warm-up. Only an
active but broken backend is degraded; blocked or disabled tools are unavailable.

Preflight requests contain only `action`, `inputs`, and `target`. They never send
a caller-selected actor identity. A preview is not authorization: invocation is
blocked unless the gateway reports it executable now. Unknown side effects fail
closed, allowed mutations require operator confirmation, and execution performs
the authoritative policy check.

HTTP 202 approval responses are modeled as pending rather than success. The UI
freezes the exact input request, requires an explicit grant, then resumes with
the gateway-bound `approval_id`, `run_id`, and `session_id`.
A normal HTTP 202 `running` response is an asynchronous acknowledgement. The UI
does not label it complete; the authoritative result arrives later as a
`tool_result` run event.

Run discovery and inspection consume event schema 1.0 through `GET /api/runs`,
`GET /api/runs/{run_id}`, and cursor replay at
`GET /api/runs/{run_id}/events`. Stream metadata observed on normal ACP turns is
preserved so `/run` can inspect the current run. Mission Control polls from the
last sequence cursor, drains `has_more` pages without delay, deduplicates by
sequence, and renders `retained_from` gaps as explicit replay resets. The replay
buffer is bounded and process-local; the UI labels missing, expired, empty,
degraded, and truncated states rather than implying durable history.

The shared terminal predicate contains exactly `run_completed`, `run_failed`,
`run_interrupted`, `run_cancelled`, and `error`. Graph-level lifecycle and output
events are progress: in particular, `graph_complete` cannot stop follow because
`final_output` and `run_completed` may still arrive.

Sensitive results remain gateway-redacted in this inspector. It does not
silently follow a claim URL or retain a revealed value; reveal-once is a
separate, explicitly gated extension rather than part of generic replay.

`session_id` is stable conversation continuity, while `run_id` identifies one
execution; neither the adapter nor the inspector assumes they are equal.

The support contract is published in
[`capability-coverage.json`](capability-coverage.json). Catalog entries default to
generated forms; dedicated Terminal UI commands are declared as native overrides.

## Service dashboard over HTTP

The Alt+D service dashboard (`screens/dashboard.py`) fetches its layout and widget
data from the backend gateway over HTTP — `GET /api/dashboard/full` and
`/api/dashboard/data` via `AgentClient` — rather than constructing the gateway
aggregator in-process. This keeps the dashboard, like everything else, free of an
in-process `agent_utilities` import; if the backend is unreachable it degrades to
a placeholder.

## Key components

| File | Purpose |
|------|---------|
| `app.py` | Main Textual application: screen composition, message queuing, exit confirmation, key bindings. Accepts an injectable `client` for testing. |
| `terminal_ui.py` | CLI entry point; parses flags and lazily dispatches to the TUI or the headless runner. |
| `headless.py` | `HeadlessRunner` + `StreamSink` + `RenderSink` protocol — the no-widget-tree run path. |
| `client.py` | ACP client, normalized SSE parsing, and capability/run/dashboard HTTP methods. |
| `capabilities.py` | Typed catalog, preflight, schema-field, invocation, and run-event models. |
| `capability_provider.py` | Live capability provider for Textual's global command palette. |
| `commands.py` | Slash-command processor with the full command set. |
| `goal.py` | Dependency-free `GoalSpec` parser for the `/goal` command (no backend import). |
| `screens/main.py` | Primary conversation screen and layout (`main.tcss`). |
| `screens/dashboard.py` | Alt+D service dashboard, fed over HTTP. |
| `screens/agent_view.py` | Multi-session dashboard (Agent View). |
| `widgets/conversation.py` | Structured message container with widget pruning. |
| `widgets/user_message.py`, `agent_response.py`, `tool_call_block.py`, `throbber.py` | Conversation message blocks. |
| `widgets/workflow.py` | Dynamic workflow sidebar with phase labels and completion markers. |
| `widgets/capability_sidebar.py` | Searchable live catalog tab with availability states. |
| `tui/animation.py` | Shared `animate_in()` entrance fade for conversation widgets (honors reduced-motion / `TEXTUAL_ANIMATIONS`). |
| `tui/input_text_area.py` | Multi-line input with the slash-command + file suggestion overlays. |
| `tui/tool_display/` | Extensible tool formatter system (registry + per-tool formatters). |
| `tui/tool_approval_screen.py` | Human-in-the-loop modal for confirming sensitive tool calls. |
| `tui/capability_palette.py` | Schema-generated action forms, preflight confirmation, and generic invocation. |
| `tui/run_inspector.py` | Run Mission Control: discovery, cursor replay, live polling, gap reporting, and terminal-aware follow. |
| `tui/status_line.py` | Mode / model / token status bar. |
| `tui/theme.py` | Theme helpers. |

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_URL` | `http://localhost:8000` | Agent backend URL (used by both interactive and headless modes). |
| `ACP_URL` | `{AGENT_URL}/acp` | Override for the ACP mount used by `client.py`'s hand-rolled JSON-RPC/SSE convention. Defaults to `{AGENT_URL}/acp` when unset. |
| `AGENT_THEME` | `tokyo-night` | Initial theme (any Textual built-in theme name). |

See [Configuration](configuration.md) for the full settings reference.

## Implementation notes

### Lightweight frontend
- No top-level or lazy `agent_utilities` import on any path; the import-guard test
  enforces this.
- `/goal` uses the vendored `goal.py` parser instead of importing the backend
  `GoalSpec` (which would drag in the package init, logfire, and opentelemetry).
- Conversation memory is bounded: the `Conversation` widget prunes to
  `max_conversation_widgets` (default 50); full history lives in SQLite.

### Message queuing
- Attribute `_user_message_queue` (named to avoid Textual conflicts).
- Related queries are combined via regex patterns (conjunctions, semicolon
  sequences, shared action verbs) and processed at `turn_end`.
- Commands: `/queue`, `/queue:clear`, `/queue:toggle`.

### Theme & motion
- Default theme `tokyo-night`; switch live with `/theme <name>` across Textual's
  built-in themes. Set `AGENT_THEME` to choose the startup theme.
- Conversation blocks fade in on mount via `tui/animation.py`. Motion honors the
  Textual animation level, so `TEXTUAL_ANIMATIONS=none` (or a reduced-motion
  environment) renders widgets immediately at rest — which is also how snapshot
  tests stay deterministic.

### Exit confirmation
- `ExitConfirmScreen` with a callback pattern; Y / N / Esc; wrapped in try/except.

## Packaging

A slim, runtime-only `Dockerfile` (python:3.13-slim) ships the frontend and its
direct dependencies — no test/shell extras, no `agent_utilities`. Point it at a
shared backend with `AGENT_URL`. Because the backend is the heavy component, run
**one** backend service and many lightweight frontends against it.
