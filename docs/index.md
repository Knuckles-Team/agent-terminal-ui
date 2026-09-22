# Agent Terminal UI

Agent Terminal UI is a Textual frontend for interactive and headless agent sessions. It renders streamed responses, tool activity, approvals, and live Graph OS capabilities.

Graph OS provides the REST capability, run, and dashboard surfaces. The chat turn uses Graph OS's authenticated A2A streaming boundary; see the [current architecture](architecture.md).

## Documentation

- [Architecture](architecture.md)
- [Configuration](configuration.md)
- [Features](features.md)
- [Session management](session_management.md)
- [Agent View](agent_view.md)
- [Goal command](goal_command.md)
- [Concept registry](concepts.md)

## Core platform

- [Epistemic Graph](https://knuckles-team.github.io/epistemic-graph/)
- [Agent Utilities](https://knuckles-team.github.io/agent-utilities/)
- [Graph OS](https://knuckles-team.github.io/graph-os/)
- [Agent Connector SDK](https://knuckles-team.github.io/agent-connector-sdk/)
- [Agent Web UI](https://knuckles-team.github.io/agent-webui/)

## Install and launch

Install the package and launch the terminal client:

```bash
python -m pip install agent-terminal-ui
agent-terminal-ui
```

Set `AGENT_URL` to the Graph OS API and `AGENT_BEARER_TOKEN` to your bearer credential before using chat. See [Configuration](configuration.md) for settings.
