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
  - `/effort` -- set reasoning effort level (low/medium/high/max)
  - `/memory` -- manage project memory (AGENTS.md)
  - `/agents` -- list available specialized agents
  - `/add-dir` -- add a directory to the agent's working context
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
agent-tui
```

Or run with `uv` if installed locally:

```bash
uv run agent-tui
```

### Keyboard Shortcuts

- **Ctrl+C** -- Interrupt generation or cancel current operation
- **Ctrl+D** -- Exit session (with confirmation)
- **Ctrl+L** -- Clear the event log
- **Ctrl+O** -- Toggle workflow sidebar
- **Ctrl+T** -- Toggle task list view
- **Ctrl+U** -- Clear input buffer
- **Ctrl+Y** -- Restore cleared input buffer
- **Alt+P** -- Switch AI model
- **Alt+T** -- Toggle Extended Thinking (for reasoning models)
- **Alt+O** -- Toggle Fast Mode
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

Set up git hooks:

```bash
prek install
```

To update dependencies (updates the lock file):

```bash
uv sync --all-groups
```

Run formatting, linting, and type checking:

```bash
uv run ruff format && uv run ruff check --fix && uv run ty check
```
