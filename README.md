# Agent Terminal UI

<p align="center"><img src="https://raw.githubusercontent.com/Knuckles-Team/pipelines/64e34ca63385200f5ddfef5286e6886bf7dc80b4/templates/mkdocs-theme/assets/brands/agent-terminal-ui-logo-v1.png" alt="Agent Terminal UI logo" width="160"></p>

[![PyPI version](https://img.shields.io/pypi/v/agent-terminal-ui)](https://pypi.org/project/agent-terminal-ui/)
[![License](https://img.shields.io/github/license/Knuckles-Team/agent-terminal-ui)](LICENSE)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-526CFE)](https://knuckles-team.github.io/agent-terminal-ui/)

Agent Terminal UI is a Textual terminal frontend for interactive and headless agent sessions. It renders streamed responses, tool activity, approvals, and live Graph OS capabilities.

## Overview

Agent Terminal UI is a user entry point alongside Geniusbot, Agent Web UI, and Graph OS messaging. It uses Graph OS REST APIs for capability discovery and invocation, run inspection, and dashboard data. The chat turn uses this repository's ACP-style JSON-RPC and SSE transport.

## Key capabilities

- Interactive terminal sessions and lightweight headless runs.
- Live capability search, schema-generated forms, and governed invocation through Graph OS.
- Run inspection with event replay, cursor tracking, and approval resumption.
- Durable local sessions, workspace snapshots, and background tasks.
- Tool approval prompts, slash commands, and a dynamic workflow sidebar.

## Documentation

- [Agent Terminal UI documentation](https://knuckles-team.github.io/agent-terminal-ui/)
- [Current architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Features](docs/features.md)
- [Session management](docs/session_management.md)
- [Epistemic Graph](https://knuckles-team.github.io/epistemic-graph/)
- [Agent Utilities](https://knuckles-team.github.io/agent-utilities/)
- [Graph OS](https://knuckles-team.github.io/graph-os/)
- [Agent Connector SDK](https://knuckles-team.github.io/agent-connector-sdk/)
- [Agent Web UI](https://knuckles-team.github.io/agent-webui/)

## Architecture

![Knuckles-Team runtime architecture](https://raw.githubusercontent.com/Knuckles-Team/pipelines/64e34ca63385200f5ddfef5286e6886bf7dc80b4/templates/mkdocs-theme/assets/runtime-architecture.svg)

Graph OS serves the REST capability, run, and dashboard surfaces used by the TUI. It does not currently mount the TUI's ACP chat endpoint. The client defaults `ACP_URL` to `{AGENT_URL}/acp`, so a compatible ACP service must be configured there for chat; Graph OS alone does not complete that path. The TUI uses its own HTTP/SSE implementation of the ACP-style protocol, not Zed's ACP SDK.

## Quick start

Install and launch with Python 3.11–3.14:

```bash
python -m pip install agent-terminal-ui
agent-terminal-ui
```

Set `AGENT_URL` to the Graph OS API and `ACP_URL` to a compatible ACP endpoint before using chat. See [Current architecture](docs/architecture.md) for the current integration boundary and [Configuration](docs/configuration.md) for settings.

## Contributing

Issues and pull requests are welcome in the [Agent Terminal UI repository](https://github.com/Knuckles-Team/agent-terminal-ui).

## License

Agent Terminal UI is released under the [MIT License](LICENSE).
