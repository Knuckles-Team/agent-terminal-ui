# Agents & Issues

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
- **Technical Note**: Fixed critical naming conflict -- renamed from `_message_queue` to `_user_message_queue` to avoid collision with Textual's internal `_message_queue` (asyncio.Queue)

### Exit Confirmation Modal (2026-04-20)
- **Decision**: Re-enable exit confirmation modal using proper Textual ModalScreen patterns
- **Implementation**: Created `ExitConfirmScreen` following Textual best practices with callback pattern
- **Features**: Proper ModalScreen implementation, keyboard navigation (Y/N/Esc), error handling, proper modal sizing
- **Outcome**: Users get confirmation dialog before exit, preventing accidental termination
- **Technical Note**: Uses `push_screen()` with callback instead of `push_screen_wait()`, fixed CSS `gap` property issue

### Terminal Transparency Support (2026-04-20)
- **Decision**: Enable terminal transparency support to respect user's terminal background settings
- **Implementation**: Changed all theme background colors to `rgba(0,0,0,0)` (fully transparent)
- **Outcome**: UI now respects terminal transparency settings
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

- Removed nine stub slash commands. Registry now has 31 functional commands plus 2 aliases.
- Theme switch keybind moved to `Alt+Shift+T` so `Ctrl+T` can alias `Ctrl+O` for sidebar toggle.
- Workflow sidebar event parsing consumes the expanded `tools-bound` payload.
- Pruned unused imports via `ruff --select F401 --fix`.
- Verified zero proprietary references in source, README.md, AGENTS.md, and environment templates.
- Pre-commit hardening pass completed (2026-04-23): all hooks pass. `no-commit-to-branch` always fails on `main` -- expected.

*Last Updated: 2026-04-23*
