# Architecture

## Protocol Connection

`agent-terminal-ui` connects to `agent-utilities` via two protocols:

- **AG-UI** (default): SSE streaming with sideband graph events (prefix `8:`). The TUI parses these events to render real-time graph activity in the workflow sidebar.
- **ACP** (opt-in via `ENABLE_ACP=true`): JSON-RPC + SSE for advanced session management, planning, and mode switching.

The TUI renders a dynamic workflow sidebar that discovers graph nodes from sideband events. Nodes are NOT hardcoded -- they appear as the graph emits `specialist_enter` / `specialist_exit` events. Phase labels (Planning, Discovery, Execution, Validation) and completion markers are derived from `routing_started`, `routing_completed`, and `verification_result` events.

The backend uses **unified specialist discovery** (`discover_all_specialists()`) to merge MCP agents and A2A peers into a single roster during graph bootstrap. Both sources emit the same sideband events, so the TUI does not need to distinguish between them. The `tools-bound` event now includes `toolset_count`, `dev_tools`, and `mcp_tools` fields for richer telemetry.

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

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_URL` | `http://localhost:8000` | Agent server URL |
| `ENABLE_ACP` | `false` | Enable ACP protocol |
| `ACP_URL` | `http://localhost:8001` | Documented but NOT read by `client.py`; effective ACP URL is derived as `{AGENT_URL}/acp` |

## Important Implementation Details

### Message Queuing System
- **Attribute**: `_user_message_queue` (NOT `_message_queue` to avoid Textual conflicts)
- **Query Combination**: Uses regex patterns for conjunctions ("and", "also", "plus"), sequential actions (semicollon), and similar structure (same action verbs)
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
