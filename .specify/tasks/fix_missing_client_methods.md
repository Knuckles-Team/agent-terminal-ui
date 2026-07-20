# Task: Fix Missing AgentClient Methods

## Priority
**P3 - Critical**: Currently blocking `/mcp`, `/history`, `/export` commands

## Description
Implement three undefined methods in `AgentClient` that are called by command handlers but don't exist, causing runtime crashes.

## Related Spec
- `.specify/specs/missing_client_methods.md`

## Dependencies
None - this is a standalone bug fix

## Definition of Done
- [ ] Implement `get_mcp_config()` returning MCP server config dict
- [ ] Implement `list_mcp_tools()` returning available MCP tools list
- [ ] Implement `list_chats()` returning chat/session IDs list
- [ ] All three methods handle errors gracefully with empty defaults
- [ ] Pre-commit hooks pass (`ruff`, `mypy`, `ty`)
- [ ] Type hints are added and consistent with existing code style
- [ ] Tests verify the new methods work correctly

## Notes
This task addresses P3-CRITICAL issues identified in self-improvement analysis. These methods should return sensible empty defaults when no agents/MCP servers are configured, maintaining backward compatibility.

## Breaking Changes
None - pure additions to `AgentClient` class

## Implementation Notes (2026-04-25)
**RED → GREEN PHASE COMPLETE**: All three missing `AgentClient` methods have been implemented with graceful error handling.

### Changes Made
1. **get_mcp_config()** - Added error handling to prevent AttributeError, returns safe empty default `{servers: [], available: False}` on failure
2. **list_mcp_tools()** - Added error handling to prevent AttributeError, returns empty list `[]` on failure
3. **list_chats()** - Already existed but had missing tests

### Test Updates
Updated test expectations to match graceful degradation behavior (tests now verify that errors are handled gracefully instead of propagating).

### Files Modified
- `agent_terminal_ui/client.py` - Added error handling to three MCP/chat-related methods
- `tests/test_client_methods.py` - Updated test expectations for graceful defaults

---

## Next Steps: Phase 2
1. Update `.specify/specs/missing_client_methods.md` with implementation notes and completion status
2. Run self-improvement scripts if available
3. Address remaining P3 issues (e.g., failing `test_theme_switch_shortcut`)
4. Consider implementing quick wins (.env.example, tool guards)
