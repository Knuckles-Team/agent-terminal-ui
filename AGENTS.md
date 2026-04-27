# General Instructions

> **Notice:** This project uses **Spec-Driven Development (SDD)**.
> - Project constitution and governance: `.specify/memory/constitution.md`.
> - Feature specifications and tasks: `.specify/specs/` and `.specify/tasks/`.
> This file (`AGENTS.md`) is for system-prompt context; the SDD directory is the source of truth for architecture and new features.
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

> **Note:** The complete specification for the **Command Registry** and keyboard shortcuts is now formally tracked in `.specify/specs/command_registry.md`.

`agent-terminal-ui` connects to `agent-utilities` via two protocols:

- **AG-UI** (default): SSE streaming with sideband graph events (prefix `8:`). The TUI parses these events to render real-time graph activity in the workflow sidebar.
- **ACP** (opt-in via `ENABLE_ACP=true`): JSON-RPC + SSE for advanced session management, planning, and mode switching.

The TUI renders a dynamic workflow sidebar that discovers graph nodes from sideband events. Nodes are NOT hardcoded -- they appear as the graph emits `specialist_enter` / `specialist_exit` events. Phase labels (Planning, Discovery, Execution, Validation) and completion markers are derived from `routing_started`, `routing_completed`, and `verification_result` events.

The backend uses **unified specialist discovery** (`discover_all_specialists()`) to merge MCP agents and A2A peers into a single roster during graph bootstrap. Both sources emit the same sideband events, so the TUI does not need to distinguish between them. The `tools-bound` event now includes `toolset_count`, `dev_tools`, and `mcp_tools` fields for richer telemetry. The backend also emits structured trace logs to `agent_utilities.graph.trace` for server-side prompt-flow tracing.

## Key Components

| File | Purpose |
|------|---------|
| `app.py` | Main Textual application, screen composition, message queuing, exit confirmation |
| `client.py` | AG-UI + ACP protocol clients (SSE parsing, event dispatch) |
| `commands.py` | Slash command processor with comprehensive command set |
| `terminal_ui.py` | CLI entry point for the `agent-tui` command |
| `widgets/workflow.py` | Dynamic workflow sidebar with phase labels and completion markers |
| `tui/input_text_area.py` | Multi-line input widget with slash-command suggestion overlay |
| `tui/tool_display/` | Extensible tool formatter system (registry + per-tool formatters) |
| `tui/tool_approval_screen.py` | Human-in-the-loop modal for confirming sensitive tool calls |
| `tui/history_screen.py` | Session management and chat history browser |
| `tui/mcp_screen.py` | MCP server browser for inspecting connected servers and tools |
| `tui/exit_confirm_screen.py` | Exit confirmation modal following Textual ModalScreen patterns |
| `tui/formatters.py` | Rich text formatting utilities for chat messages |
| `tui/theme.py` | Theme system with transparency support and color semantics |
| `tui/css.py` | Textual CSS styling definitions |

## Important Implementation Details

### Message Queuing System
- **Attribute**: `_user_message_queue` (NOT `_message_queue` to avoid Textual conflicts)
- **Query Combination**: Uses regex patterns for conjunctions ("and", "also", "plus"), sequential actions (semicolon), and similar structure (same action verbs)
- **Processing**: Automatic queue processing at turn_end events
- **Commands**: `/queue`, `/queue:clear`, `/queue:toggle`

### Theme System
- **Transparency**: All themes use `rgba(0,0,0,0)` for backgrounds to respect terminal transparency
- **Surface Colors**: Semi-transparent backgrounds for panels (`$surface` variable)
- **Available Themes**: modern_dark (default), modern_light, nord, gruvbox
- **CSS Variables**: Uses Textual's `$background`, `$surface`, `$primary`, etc.

### Exit Confirmation
- **Implementation**: `ExitConfirmScreen` with callback pattern (NOT `push_screen_wait()`)
- **Keyboard Shortcuts**: Y (yes), N (no), Esc (cancel)
- **Error Handling**: Wrapped in try-except to prevent crashes during exit
- **CSS**: Uses margin-based spacing instead of invalid `gap` property

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_URL` | `http://localhost:8000` | Agent server URL |
| `ENABLE_ACP` | `false` | Enable ACP protocol |
| `ACP_URL` | `http://localhost:8001` | Documented but NOT read by `client.py`; effective ACP URL is derived as `{AGENT_URL}/acp` |

## Slash Commands

Registered in `commands.py` via the `self.commands` dict. Current registry: 31 commands plus 2 aliases.

**Implemented**: `/help`, `/clear`, `/exit` (alias `/quit`), `/mcp`, `/history`, `/image`, `/plan`, `/chat`, `/build`, `/init`, `/review`, `/test`, `/search`, `/stats` (alias `/cost`), `/model`, `/theme`, `/queue`, `/queue:clear`, `/queue:toggle`, `/compact`, `/context`, `/diff`, `/recap`, `/export`, `/focus`, `/fast`, `/keybindings`, `/memory`, `/agents`, `/simplify`, `/add-dir`.

### `/model` command

The `/model` command is backed by the `agent-utilities` multi-model registry
(`GET /models`):

- `/model` or `/model list` -- render the configured models in a Rich table
  (id, name, provider, tier, tags, default marker, per-1M cost).
- `/model show` -- show a Panel with full metadata for the currently active
  model (falls back to the registry default when no override is set).
- `/model set <id>` -- pick a model id for subsequent turns. The chosen id
  is stored on both `app._current_model_id` and `app._current_model`, and
  the `AgentClient` propagates it as an `x-agent-model-id` header so the
  backend can override the registry default for the session.

Zero-cost / local models (`cost: {input: 0, output: 0}`) render as
`$0.00 / $0.00` in the table rather than `-`, so tokens and tool counts
remain visible even when the model itself is free.

**Removed this session** (nine stub commands with no working implementation): `/effort`, `/permissions`, `/color`, `/hooks`, `/branch` / `/fork`, `/copy`, `/undo` / `/rewind`, `/loop` / `/proactive`, `/btw`. Removing them keeps the slash menu aligned with the actual supported feature set.

Note: `/mcp`, `/history`, and `/export` are still listed as implemented but currently raise `AttributeError` at runtime due to missing `AgentClient` methods (see Known Issues).

## Keyboard Shortcuts

Claude-code parity bindings are wired in `agent_terminal_ui/app.py::BINDINGS`. Summary of the current mapping:

| Binding | Action |
|---|---|
| `Ctrl+L` | Clear log |
| `Ctrl+O` | Toggle sidebar |
| `Ctrl+T` | Toggle sidebar (aliased to `Ctrl+O` so both work) |
| `Ctrl+R` | Reverse search |
| `Ctrl+U` / `Ctrl+Y` | Clear / restore input |
| `Ctrl+H` | Show help |
| `Ctrl+G` | Open in editor |
| `Ctrl+B` | Background tasks |
| `Alt+P` | Model picker |
| `Alt+T` | Toggle extended thinking |
| `Alt+O` | Toggle fast mode |
| `Alt+Shift+T` | Switch theme (moved off `Ctrl+T`, which is now the sidebar alias) |
| `Shift+Tab` | Cycle mode |
| `Esc Esc` | Rewind |
| `!` (input prefix) | Direct bash execution |

**Planned (not yet implemented)**: `@` file-mention autocomplete prefix.

## Known Issues

**P3-CRITICAL**:
- Three `AgentClient` methods are called by `commands.py` but not defined on the client: `get_mcp_config()`, `list_mcp_tools()`, `list_chats()`. Invoking `/mcp`, `/history`, or `/export` raises `AttributeError` at runtime.
- `commands.py` references `self.app.current_session_id` and `self.app.agent_client`, but `app.py` exposes these as `_current_session_id` and `_client`. Access raises `AttributeError`.

**P3-HIGH**:
- `tests/test_enhanced_features.py::TestKeyboardShortcuts::test_theme_switch_shortcut` is failing (103 of 104 tests pass).

## Recent Changes

### Message Queuing System (2026-04-20)
- **Decision**: Implement message queuing with query combination support similar to Devin's behavior
- **Implementation**: Added `_user_message_queue` attribute to AgentApp with query combination logic
- **Features**: Queues messages when agent is processing, combines related queries using regex patterns, slash commands for queue management
- **Outcome**: Users can type multiple commands while agent is processing; related queries are intelligently combined
- **Technical Note**: Fixed critical naming conflict - renamed from `_message_queue` to `_user_message_queue` to avoid collision with Textual's internal `_message_queue` (asyncio.Queue)

### Exit Confirmation Modal (2026-04-20)
- **Decision**: Re-enable exit confirmation modal using proper Textual ModalScreen patterns
- **Implementation**: Created `ExitConfirmScreen` following Textual best practices with callback pattern
- **Features**: Proper ModalScreen implementation, keyboard navigation (Y/N/Esc), error handling, proper modal sizing
- **Outcome**: Users get confirmation dialog before exit, preventing accidental termination
- **Technical Note**: Uses `push_screen()` with callback instead of `push_screen_wait()`, fixed CSS `gap` property issue

### Terminal Transparency Support (2026-04-20)
- **Decision**: Enable terminal transparency support to respect user's terminal background settings
- **Implementation**: Changed all theme background colors to `rgba(0,0,0,0)` (fully transparent)
- **Outcome**: UI now respects terminal transparency settings like Devin does
- **Technical Note**: Textual CSS doesn't support "default" keyword, used `rgba(0,0,0,0)` for transparency

### Prior Architecture Updates
- Dynamic WorkflowSidebar with runtime node discovery from sideband events
- Enhanced sideband event parsing for specialist lifecycle and routing events
- Extensible tool display formatter system with registry-based dispatch
- Human-in-the-loop tool approval screen for sensitive operations
- Multi-modal image attachment support
- MCP server browser screen
- Unified specialist discovery merging MCP agents and A2A peers
- Real-time token and cost tracking in StatusLine widget
- ACP protocol support for advanced session management and planning

## Session Journal (consolidated)

Single-read summary of what landed in the recent consolidation work. Detail lives in the sections above.

- Removed nine stub slash commands (`/effort`, `/permissions`, `/color`, `/hooks`, `/branch`/`fork`, `/copy`, `/undo`/`rewind`, `/loop`/`proactive`, `/btw`). Registry now has 31 functional commands plus 2 aliases.
- Theme switch keybind moved to `Alt+Shift+T` so `Ctrl+T` can alias `Ctrl+O` for sidebar toggle, matching Claude Code parity.
- Workflow sidebar event parsing consumes the expanded `tools-bound` payload (`toolset_count`, `dev_tools`, `mcp_tools`) and the structured trace logs now emitted by the backend at `agent_utilities.graph.trace`.
- Pruned unused imports via `ruff --select F401 --fix` in the local package.
- Verified zero proprietary references in source, README.md, AGENTS.md, and the environment templates.
- Known issues remain: three `AgentClient` methods missing (`get_mcp_config`, `list_mcp_tools`, `list_chats`), and one keyboard-shortcut test still failing. Both tracked as P3.
- Pre-commit hardening pass completed (2026-04-23): all hooks (`ruff`, `ruff-format`, `mypy`, `vulture`, `bandit`, `codespell`) pass. `no-commit-to-branch` always fails on `main` — expected.

*Last Updated: 2026-04-23*
