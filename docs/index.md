# agent-terminal-ui

`agent-terminal-ui` is a [Textual](https://textual.textualize.io/)-based terminal
user interface for interacting with AI agents built on the
[agent-utilities](https://github.com/pydantic/agent-utilities) platform. It connects
to an agent backend over dual protocols — AG-UI (SSE streaming) and ACP
(JSON-RPC + SSE) — and renders live workflow activity, tool execution, and
human-in-the-loop approvals in the terminal.

This site is the official documentation for the client: its architecture, configuration
surface, durable session infrastructure, and the autonomous goal and multi-session
workflows it supports.

## Documentation map

- **[Architecture](architecture.md)** — protocol connectivity, key components,
  environment variables, and implementation details.
- **[Features](features.md)** — slash commands, keyboard shortcuts, and the model picker.
- **[Configuration](configuration.md)** — the complete settings reference, hooks
  configuration, and sandbox modes.
- **[Session Management](session_management.md)** — durable session persistence,
  pre-turn checkpointing, crash recovery, and workspace snapshots.
- **[Agent View](agent_view.md)** — the multi-session dashboard and background agent
  management.
- **[Goal Command](goal_command.md)** — the autonomous `/goal` loop and its
  Knowledge-Graph-native integration.
- **[Agents & Issues](agents.md)** — known issues, recent changes, and the session journal.
- **[Concepts](concepts.md)** — the stable concept registry (`CONCEPT:TUI-*`) tracing
  the client's core ideas across documentation and source.

## Installation

The client is published on [PyPI](https://pypi.org/project/agent-terminal-ui/):

```bash
pip install agent-terminal-ui
```

Launch the terminal interface:

```bash
agent-terminal-ui
```

Consult the [Configuration](configuration.md) reference to point the client at your
agent backend and tune its behavior.
