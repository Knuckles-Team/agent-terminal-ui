# General Instructions
- This is a production-grade Python package. You must *always* follow best open-source Python practices.
- Shortcuts are not appropriate. When in doubt, you must work with the user for guidance.
- Any documentation you write, including in the README.md, should be clear, concise, and accurate like the official documentation of other production-grade Python packages.
- Make sure any comments in code are necessary. A necessary comment captures intent that cannot be encoded in names, types, or structure. Comments should be reserved for the "why", only used to record rationale, trade-offs, links to specs/papers, or non-obvious domain insights. They should add signal that code cannot.
- The current code in the package should be treated as an example of high quality code. Make sure to follow its style and tackle issues in similar ways where appropriate.
- Anything is possible. Do not blame external factors after something doesn't work on the first try. Instead, investigate and test assumptions through debugging through first principles.

# Python Development Instructions
- `ty` by Astral is used for type checking. Always add appropriate type hints such that the code would pass ty's type check.
- Follow the Google Python Style Guide.
- After each code change, checks are automatically run. Fix any issues that arise.
- **IMPORTANT**: The checks will remove any unused imports after you make an edit to a file. So if you need to use a new import, be sure to use it FIRST (or do your edits at the same time) or else it will be automatically removed. DO NOT use local imports to get around this.
- Always prefer pathlib for dealing with files. Use `Path.open` instead of `open`.
- When using pathlib, **always** Use `.parents[i]` syntax to go up directories instead of using `.parent` multiple times.
- When writing tests, use pytest and pytest-asyncio.
- Prefer using loguru for logging instead of the built-in logging module. Do not add logging unless requested.
- NEVER use `# type: ignore`. It is better to leave the issue and have the user work with you to fix it.
- Don't put types in quotes unless it is absolutely necessary to avoid circular imports and forward references.

# Documentation Instructions
- Keep it very concise
- No emojis or em dashes.

# Key Files

@README.md

@pyproject.toml

# Architecture

`agent-terminal-ui` connects to `agent-utilities` via two protocols:

- **AG-UI** (default): SSE streaming with sideband graph events (prefix `8:`). The TUI parses these events to render real-time graph activity in the workflow sidebar.
- **ACP** (opt-in via `ENABLE_ACP=true`): JSON-RPC + SSE for advanced session management, planning, and mode switching.

The TUI renders a dynamic workflow sidebar that discovers graph nodes from sideband events. Nodes are NOT hardcoded -- they appear as the graph emits `specialist_enter` / `specialist_exit` events. Phase labels (Planning, Discovery, Execution, Validation) and completion markers are derived from `routing_started`, `routing_completed`, and `verification_result` events.

The backend uses **unified specialist discovery** (`discover_all_specialists()`) to merge MCP agents and A2A peers into a single roster during graph bootstrap. Both sources emit the same sideband events, so the TUI does not need to distinguish between them. The `tools-bound` event now includes `toolset_count`, `dev_tools`, and `mcp_tools` fields for richer telemetry. The backend also emits structured trace logs to `agent_utilities.graph.trace` for server-side prompt-flow tracing.

## Key Components

| File | Purpose |
|------|---------|
| `app.py` | Main Textual application and screen composition |
| `client.py` | AG-UI + ACP protocol clients (SSE parsing, event dispatch) |
| `commands.py` | Slash command processor (`/help`, `/clear`, `/mcp`, `/history`, `/image`) |
| `terminal_ui.py` | CLI entry point for the `agent-tui` command |
| `widgets/workflow.py` | Dynamic workflow sidebar with phase labels and completion markers |
| `tui/tool_display/` | Extensible tool formatter system (registry + per-tool formatters) |
| `tui/tool_approval_screen.py` | Human-in-the-loop modal for confirming sensitive tool calls |
| `tui/history_screen.py` | Session management and chat history browser |
| `tui/mcp_screen.py` | MCP server browser for inspecting connected servers and tools |
| `tui/formatters.py` | Rich text formatting utilities for chat messages |
| `tui/css.py` | Textual CSS styling definitions |

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_URL` | `http://localhost:8000` | Agent server URL |
| `ENABLE_ACP` | `false` | Enable ACP protocol |
| `ACP_URL` | `http://localhost:8001` | ACP server URL |

## Recent Changes

- Dynamic WorkflowSidebar: nodes discovered from sideband events, phase labels (Planning/Discovery/Execution/Validation), completion markers
- Enhanced sideband event parsing: `specialist_enter`/`specialist_exit`, `routing_started`/`routing_completed`, `verification_result`
- Fixed missing CLI entry point (`terminal_ui.py`)
- ACP event mapping for graph transparency
- Extensible tool display formatter system with registry-based dispatch
- Human-in-the-loop tool approval screen for sensitive operations
- Multi-modal image attachment support
- MCP server browser screen
- Backend now uses unified specialist discovery (`discover_all_specialists()`): MCP agents and A2A peers merged into a single `DiscoveredSpecialist` roster. The TUI consumes identical sideband events from both sources.
- `tools-bound` sideband event now includes `toolset_count`, `dev_tools`, and `mcp_tools` for richer tool-binding telemetry
- Backend emits structured trace logs to `agent_utilities.graph.trace` for server-side prompt-flow tracing without the TUI
