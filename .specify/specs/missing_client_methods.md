# Missing AgentClient Methods Specification

## Overview
Address critical P3 issues where `AgentClient` methods are undefined but called by command handlers, causing `AttributeError` crashes.

## User Stories
- **US-001**: As a User, I want the `/mcp` command to work without crashing when checking MCP server configuration.
- **US-002**: As a User, I want the `/history` command to list chat sessions without raising `AttributeError`.
- **US-003**: As a User, I want the `/export` command to export sessions without undefined method errors.

## Functional Requirements
- **FR-001 (get_mcp_config)**: Implement `get_mcp_config()` method returning MCP server configuration dict or empty config if no servers connected.
- **FR-002 (list_mcp_tools)**: Implement `list_mcp_tools()` method returning list of available MCP tools with names and descriptions.
- **FR-003 (list_chats)**: Implement `list_chats()` method returning list of active chat/session IDs.

## API Contract

### get_mcp_config() -> dict
```python
{
    "servers": [
        {"id": "server1", "name": "First Server", "url": "http://localhost:6008"}
    ],
    "connected_count": 0,
    "available": True
}
```

### list_mcp_tools() -> list[dict]
```python
[
    {"name": "list_projects", "description": "List available projects"},
    {"name": "read_file", "description": "Read a file from disk"}
]
```

### list_chats() -> list[str]
```python
["session_001", "session_002"]
```

## Non-Functional Requirements
- **NFR-001**: All methods must handle connection errors gracefully with empty defaults.
- **NFR-002**: Methods must be idempotent and safe for concurrent access.
- **NFR-003**: Return types must match the JSON schema in `client.py` type hints.

## Acceptance Criteria
- ✅ Calling `/mcp` no longer raises `AttributeError: 'AgentClient' object has no attribute 'get_mcp_config'`
- ✅ Calling `/history` displays chat list (or "No sessions yet") instead of crashing
- ✅ Calling `/export` handles empty session list gracefully
- ✅ All pre-commit hooks pass after implementation
- ✅ Type hints match existing `AgentClient` pattern

## Implementation Location
- **File**: `agent_terminal_ui/client.py`
- **Class**: `AgentClient`
- **Method Pattern**: Follow existing method conventions in the class.

## Success Criteria
- Zero runtime errors when invoking /mcp, /history, /export commands
- Pre-commit hooks pass without failures
- Type checking passes with `ty`
