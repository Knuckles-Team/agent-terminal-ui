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

- **Dual protocol support** -- AG-UI (SSE streaming, default) and ACP (JSON-RPC + SSE, opt-in)
- **Dynamic workflow sidebar** -- discovers graph nodes from sideband events at runtime; nodes are never hardcoded
- **Phase labels** -- Planning, Discovery, Execution, Validation
- **Completed node markers** -- checkmarks on finished specialists
- **Rich tool execution display** -- extensible formatter system for rendering tool calls and results
- **Human-in-the-loop tool approval** -- modal for confirming sensitive tool calls before execution
- **Multi-modal image attachment** -- attach images to messages for visual reasoning
- **Session management and chat history** -- browse and resume previous conversations
- **MCP server browser** -- inspect connected MCP servers and their tools
- **Slash commands** -- `/help`, `/clear`, `/mcp`, `/history`, `/image`
- **Unified specialist visibility** -- MCP agents and A2A peers appear identically in the workflow sidebar; both emit the same sideband events via the backend's `discover_all_specialists()` unified roster
- **Tool-count telemetry** -- `tools-bound` sideband events include `toolset_count`, `dev_tools`, and `mcp_tools` breakdowns for per-specialist visibility


## Usage

Start the `agent-utilities` backend server, then launch the TUI:

```bash
agent-tui
```

Or run with `uv` if installed locally:

```bash
uv run agent-tui
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_URL` | `http://localhost:8000` | Agent server URL |
| `ENABLE_ACP` | `false` | Enable ACP protocol instead of AG-UI |
| `ACP_URL` | `http://localhost:8001` | ACP server URL (when ACP is enabled) |


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
