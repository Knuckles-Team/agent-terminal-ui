# Features

## Slash commands

Commands are registered in `commands.py` (`CommandProcessor.commands`) and surfaced
through the input overlay: type `/` to open a fuzzy-filtered menu (ESC to close,
TAB to cycle, Enter to run). Aliases are collapsed in the menu, so `/exit` and its
alias `/quit` appear once.

The registry currently exposes 54 entries (including aliases and `:`-suffixed
subcommands). By area:

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
| Project & SDD | `/init`, `/sdd`, `/memory`, `/add-dir`, `/prompts`, `/review`, `/test`, `/simplify` |
| MCP & tools | `/mcp`, `/mcp:reload`, `/tools`, `/skills`, `/resources` |
| Ops | `/logs`, `/cron`, `/pipeline`, `/maintenance` |

Some commands depend on optional backend endpoints and degrade or report an error
when the backend does not expose them — see [Known Issues](agents.md#known-issues).

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
