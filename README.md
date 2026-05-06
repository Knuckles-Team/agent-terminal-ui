<h1 align="center">
    agent-terminal-ui
</h1>
<p align="center">
    <p align="center">Terminal user interface for AI agents built on <a href="https://github.com/pydantic/agent-utilities">agent-utilities</a>.</p>
</p>
<p align="center">
    <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"></a>
    <a href="https://github.com/astral-sh/ty"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json" alt="ty"></a>
    <a href="https://pypi.org/project/agent-terminal-ui/"><img src="https://img.shields.io/pypi/v/agent-terminal-ui" alt="PyPI"></a>
    <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

A [Textual](https://textual.textualize.io/)-based terminal interface for interacting with AI agents. Connects to an [agent-utilities](https://github.com/pydantic/agent-utilities) backend via dual protocol support: AG-UI (SSE streaming) and ACP (JSON-RPC + SSE).

> [!NOTE]
> This library is in early development and subject to change.

### Features

#### Core Functionality
- **Dual protocol support** -- AG-UI (SSE streaming, default) and ACP (JSON-RPC + SSE, opt-in)
- **Dynamic workflow sidebar** -- discovers graph nodes from sideband events at runtime; nodes are never hardcoded
- **Phase labels** -- Planning, Discovery, Execution, Validation
- **Completed node markers** -- checkmarks on finished specialists
- **Rich tool execution display** -- extensible formatter system for rendering tool calls and results
- **Human-in-the-loop tool approval** -- modal for confirming sensitive tool calls before execution
- **Multi-modal image attachment** -- attach images to messages for visual reasoning
- **Session management and chat history** -- browse and resume previous conversations
- **MCP server browser** -- inspect connected MCP servers and their tools

#### Session Persistence & Crash Recovery (TUI-1)
- **SQLite-backed sessions** -- durable session storage at `~/.config/agent-terminal-ui/agent_terminal_ui.db`
- **Pre-turn checkpointing** -- automatic checkpoints before each turn for crash recovery
- **Session fork/resume** -- fork sessions at any turn number with `fork_session()`
- **Offline queue** -- messages queued during disconnection survive process restarts
- **Session archive** -- archive, search, and filter sessions by status

#### Workspace Snapshots & Rollback (TUI-2)
- **Side-git snapshots** -- pre/post-turn workspace snapshots without touching your `.git`
- **Snapshot restore** -- `/restore N` to roll back workspace to any previous turn
- **Diff viewer** -- view changes between snapshot points
- **Auto-pruning** -- snapshots older than configurable max age are cleaned up

#### Reasoning Effort Tiers & Auto Routing (TUI-3)
- **Three-tier reasoning** -- OFF / HIGH / MAX with `Shift+Tab` cycling
- **Auto model routing** -- lightweight heuristic selects optimal model and thinking level per turn
- **Mode-aware defaults** -- plan/code modes default to higher reasoning

#### Context Compaction Engine (TUI-4)
- **Multi-tier compaction** -- L1 (summarize tools), L2 (summarize old turns), L3 (drop old), Cycle (hard reset)
- **Configurable thresholds** -- token-based triggers at 192k/384k/576k/768k
- **Auto-compact toggle** -- automatic compaction when context window pressure is detected
- **Manual `/compact`** -- force compaction at any tier

#### Durable Task Queue (TUI-5)
- **SQLite-backed tasks** -- background tasks survive process restarts
- **Bounded concurrency** -- configurable maximum concurrent tasks
- **Timeline events** -- full event log per task (created, started, progress, completed/failed)
- **Checklist tracking** -- structured checklist state per task
- **Crash recovery** -- interrupted tasks are automatically marked as failed on restart

#### Lifecycle Hooks (TUI-6)
- **TOML-configured hooks** -- shell commands triggered on lifecycle events
- **Supported events** -- `session_start`, `session_end`, `message_submit`, `tool_call_before/after`, `mode_change`, `on_error`, `shell_env`
- **Timeout protection** -- hooks are killed after configurable timeout
- **Conditional triggers** -- hooks can fire only for specific tool categories or modes
- **Shell env injection** -- `shell_env` hooks inject environment variables into tool execution

#### Desktop Notifications (TUI-7)
- **OSC 9 / BEL notifications** -- terminal-native notifications on long-running turn completion
- **Auto-detection** -- detects iTerm2, Ghostty, WezTerm, Kitty, and falls back to BEL
- **Configurable threshold** -- only fires when turn exceeds N seconds (default: 30s)

#### Workspace Boundary & Trust Mode (TUI-8)
- **Three sandbox modes** -- `read-only`, `workspace-write` (default), `danger-full-access`
- **Trust mode** -- bypass approval for non-destructive reads outside workspace
- **Explicit allow/deny lists** -- fine-grained path-level control
- **Violation tracking** -- all policy violations are logged

#### Draft Stash System (TUI-9)
- **Multi-entry stash** -- `Ctrl+S` to stash, `/stash list` and `/stash pop` to manage
- **Buffer management** -- `Ctrl+U` clear + `Ctrl+Y` restore for single buffer

#### Enhanced Cost Tracking (TUI-10)
- **Per-turn breakdown** -- input/output/cached/reasoning token counts with cost
- **Cache hit rate** -- per-turn and session-level cache utilization metrics
- **Pricing registry** -- configurable per-model pricing (built-in for GPT-4o, Claude, DeepSeek)
- **Session aggregation** -- total cost, tokens, and by-model grouping
- **Status line display** -- compact token/cost indicator

#### Approval Policy Engine (TUI-11)
- **Three policies** -- `on-request` (ask per command), `auto` (YOLO), `never` (block all)
- **Auto-allow prefixes** -- commands matching configured prefixes bypass approval
- **Mode-aware strictness** -- plan mode requires approval for unknown commands
- **Integration** -- extends existing `danger.py` 4-level classification

#### Job Center (TUI-12)
- **Shell job registry** -- tracks all shell commands with status, output, and timing
- **Output tailing** -- last 50 lines of output per job
- **Linked tasks** -- jobs can reference durable task IDs
- **Job lifecycle** -- running → completed/failed/cancelled with cleanup

#### User Experience
- **Message queuing** -- queue messages while agent is processing; related queries are intelligently combined using regex patterns for conjunctions, sequential actions, and similar structure
- **Exit confirmation** -- modal dialog prevents accidental termination via Ctrl+C or `/exit`
- **Terminal transparency** -- UI respects your terminal's transparency settings for seamless integration
- **Theme system** -- multiple built-in themes (modern_dark, modern_light, nord, gruvbox) with proper color semantics

#### Commands
- **Slash commands** -- comprehensive command set for common operations:
  - `/help` -- show available commands
  - `/clear` -- clear the current event log
  - `/mcp` -- browse connected MCP servers and their tools
  - `/history` -- browse and select from historical chat sessions
  - `/image` -- attach images to messages
  - `/init` -- initialize a new project or workspace
  - `/review` -- review code and suggest improvements
  - `/test` -- run tests on the current codebase
  - `/search` -- search through code and documentation
  - `/stats` -- show statistics about the current session
  - `/cost` -- show token and cost tracking information
  - `/queue` -- show current message queue status
  - `/queue:clear` -- clear all queued messages
  - `/queue:toggle` -- enable/disable message queuing
  - `/model` -- switch between available AI models
  - `/theme` -- switch between available themes
  - `/compact` -- compact conversation context to save tokens
  - `/diff` -- show interactive diff viewer for recent changes
  - `/recap` -- summarize the session context
  - `/fast` -- toggle fast mode (Haiku/Flash models)
  - `/memory` -- manage project memory (AGENTS.md)
  - `/agents` -- list available specialized agents
  - `/add-dir` -- add a directory to the agent's working context
  - `/restore N` -- restore workspace to snapshot at turn N
  - `/sessions` -- list and manage durable sessions
  - `/trust` -- toggle trust mode
  - `/sandbox` -- set sandbox mode (read-only / workspace-write / danger-full-access)
  - `/approve` -- set approval policy (on-request / auto / never)
  - `/jobs` -- list and manage shell jobs
  - `/tasks` -- list and manage background tasks
  - `/stash` -- manage input draft stash
  - `/hooks` -- show lifecycle hook status
  - `/exit`, `/quit` -- exit the application with confirmation

#### Input Prefixes
- **`!`** -- Direct Bash execution (e.g., `!ls -la`)
- **`@`** -- Fuzzy file mention autocomplete (e.g., `@app.py`)

#### Backend Integration
- **Unified specialist visibility** -- MCP agents and A2A peers appear identically in the workflow sidebar; both emit the same sideband events via the backend's `discover_all_specialists()` unified roster
- **Tool-count telemetry** -- `tools-bound` sideband events include `toolset_count`, `dev_tools`, and `mcp_tools` breakdowns for per-specialist visibility
- **Real-time token and cost tracking** -- integrated in the status line for session monitoring
- **Memory Auto-loading** -- backend automatically includes `AGENTS.md` and `MEMORY.md` in the system prompt for project-aware reasoning.


## Usage

Start the `agent-utilities` backend server, then launch the TUI:

```bash
agent-terminal-ui
```

Or run with `uv` if installed locally:

```bash
uv run agent-terminal-ui
```

### Keyboard Shortcuts

- **Ctrl+C** -- Interrupt generation or cancel current operation
- **Ctrl+D** -- Exit session (with confirmation)
- **Ctrl+L** -- Clear the event log
- **Ctrl+O** -- Toggle workflow sidebar
- **Ctrl+S** -- Stash current input draft
- **Ctrl+T** -- Toggle task list view
- **Ctrl+U** -- Clear input buffer
- **Ctrl+Y** -- Restore cleared input buffer
- **Alt+P** -- Switch AI model
- **Alt+T** -- Toggle Extended Thinking (for reasoning models)
- **Alt+O** -- Toggle Fast Mode
- **Shift+Tab** -- Cycle reasoning effort (OFF → HIGH → MAX)
- **Ctrl+R** -- Reverse history search
- **Ctrl+H** -- Show help overlay
- **Tab** -- Navigate between focusable elements
- **Esc Esc** -- Rewind/Undo (experimental)

### Message Queuing

When the agent is processing, your input is automatically queued. The system intelligently combines related queries using patterns like:

- **Conjunctions**: "and", "also", "plus", "then", "after that"
- **Sequential actions**: semicolon-separated commands
- **Similar structure**: same action verbs (fix, add, remove, update, create, delete, implement, refactor)

Example: If you type "fix the bug in app.py" followed by "and add a test for it", these will be combined into a single query.

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_URL` | `http://localhost:8000` | Agent server URL |
| `ENABLE_ACP` | `false` | Enable ACP protocol instead of AG-UI |
| `ACP_URL` | `http://localhost:8001` | ACP server URL (when ACP is enabled) |

### Themes

The TUI supports multiple themes that respect terminal transparency:

- **modern_dark** (default) -- Dark theme with blue accents
- **modern_light** -- Light theme with proper contrast
- **nord** -- Nord color palette with frosty aesthetics
- **gruvbox** -- Gruvbox retro color scheme

Switch themes using `/theme <name>` command.


## Development

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [prek](https://github.com/j178/prek/blob/master/README.md#installation)

### Setup

Create uv virtual environment and install dependencies:

```bash
uv sync --frozen --all-groups
```

To update dependencies (updates the lock file):

```bash
uv sync --all-groups
```

Run formatting, linting, and type checking:

```bash
uv run ruff format && uv run ruff check --fix && uv run ty check
```
