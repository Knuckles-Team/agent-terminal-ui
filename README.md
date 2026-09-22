# Agent Terminal UI

<p align="center"><img src="docs/assets/brands/agent-terminal-ui-logo-v1.png" alt="Agent Terminal UI logo" width="160"></p>

<p align="center"><strong>A terminal interface for agent sessions and Graph OS capabilities.</strong><br><sub>Inspect work, invoke governed tools, and manage sessions from Textual.</sub></p>

[![PyPI - Version](https://img.shields.io/pypi/v/agent-terminal-ui)](https://pypi.org/project/agent-terminal-ui/) [![PyPI - Downloads](https://img.shields.io/pypi/dd/agent-terminal-ui)](https://pypi.org/project/agent-terminal-ui/) [![PyPI - License](https://img.shields.io/pypi/l/agent-terminal-ui)](https://pypi.org/project/agent-terminal-ui/) [![PyPI - Wheel](https://img.shields.io/pypi/wheel/agent-terminal-ui)](https://pypi.org/project/agent-terminal-ui/) [![PyPI - Implementation](https://img.shields.io/pypi/implementation/agent-terminal-ui)](https://pypi.org/project/agent-terminal-ui/)

[![GitHub Repo stars](https://img.shields.io/github/stars/Knuckles-Team/agent-terminal-ui)](https://github.com/Knuckles-Team/agent-terminal-ui) [![GitHub forks](https://img.shields.io/github/forks/Knuckles-Team/agent-terminal-ui)](https://github.com/Knuckles-Team/agent-terminal-ui) [![GitHub contributors](https://img.shields.io/github/contributors/Knuckles-Team/agent-terminal-ui)](https://github.com/Knuckles-Team/agent-terminal-ui) [![GitHub license](https://img.shields.io/github/license/Knuckles-Team/agent-terminal-ui)](agent_terminal_ui/LICENSE) [![GitHub last commit (by committer)](https://img.shields.io/github/last-commit/Knuckles-Team/agent-terminal-ui)](https://github.com/Knuckles-Team/agent-terminal-ui/commits/main)

[![GitHub pull requests](https://img.shields.io/github/issues-pr/Knuckles-Team/agent-terminal-ui)](https://github.com/Knuckles-Team/agent-terminal-ui/pulls) [![GitHub closed pull requests](https://img.shields.io/github/issues-pr-closed/Knuckles-Team/agent-terminal-ui)](https://github.com/Knuckles-Team/agent-terminal-ui/pulls?q=is%3Apr+is%3Aclosed) [![GitHub issues](https://img.shields.io/github/issues/Knuckles-Team/agent-terminal-ui)](https://github.com/Knuckles-Team/agent-terminal-ui/issues) [![GitHub top language](https://img.shields.io/github/languages/top/Knuckles-Team/agent-terminal-ui)](https://github.com/Knuckles-Team/agent-terminal-ui) [![GitHub language count](https://img.shields.io/github/languages/count/Knuckles-Team/agent-terminal-ui)](https://github.com/Knuckles-Team/agent-terminal-ui) [![GitHub repo size](https://img.shields.io/github/repo-size/Knuckles-Team/agent-terminal-ui)](https://github.com/Knuckles-Team/agent-terminal-ui) [![GitHub repo file count (file type)](https://img.shields.io/github/directory-file-count/Knuckles-Team/agent-terminal-ui)](https://github.com/Knuckles-Team/agent-terminal-ui)

[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-526CFE)](https://knuckles-team.github.io/agent-terminal-ui/)

<p align="center"><a href="https://knuckles-team.github.io/agent-terminal-ui/">Documentation</a> · <a href="https://knuckles-team.github.io/agent-terminal-ui/capabilities/">Capabilities</a> · <a href="https://knuckles-team.github.io/agent-terminal-ui/interfaces/">Interfaces</a> · <a href="https://knuckles-team.github.io/agent-terminal-ui/status/">Status</a></p>

## Overview

Agent Terminal UI is a Textual frontend for interactive and headless agent sessions. It uses Graph OS REST APIs for live capability discovery and invocation, run inspection, and dashboard data. Its ACP-style chat transport is separate and requires a compatible endpoint.

## Key capabilities

- Interactive terminal sessions and lightweight headless runs.
- Live capability search, schema-generated forms, and governed invocation through Graph OS.
- Run inspection with event replay, cursor tracking, and approval resumption.
- Durable local sessions and workspace snapshots, background tasks, slash commands, tool approvals, and a dynamic workflow sidebar.

## Documentation

- [Documentation home](https://knuckles-team.github.io/agent-terminal-ui/)
- [Capabilities](https://knuckles-team.github.io/agent-terminal-ui/capabilities/)
- [Interfaces](https://knuckles-team.github.io/agent-terminal-ui/interfaces/)
- [Status](https://knuckles-team.github.io/agent-terminal-ui/status/)
- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- Core projects: [Epistemic Graph](https://knuckles-team.github.io/epistemic-graph/), [Agent Utilities](https://knuckles-team.github.io/agent-utilities/), [Graph OS](https://knuckles-team.github.io/graph-os/), [Agent Connector SDK](https://knuckles-team.github.io/agent-connector-sdk/), and [Agent Web UI](https://knuckles-team.github.io/agent-webui/).

## Architecture

![Knuckles-Team runtime architecture](docs/assets/runtime-architecture.svg)

Graph OS serves the REST capability, run, and dashboard surfaces used by this client. The main chat path uses this repository's HTTP/SSE ACP-style transport, which the current Graph OS deployment does not mount. A compatible ACP endpoint is required for chat; this project does not use Zed's ACP SDK.

## Quick start

Install and launch with Python 3.11–3.14:

```bash
python -m pip install agent-terminal-ui
agent-terminal-ui
```

Set `AGENT_URL` to the Graph OS API and `ACP_URL` to a compatible ACP endpoint before using chat. See [Configuration](docs/configuration.md) for settings.

## Contributing

Issues and pull requests are welcome in the [Agent Terminal UI repository](https://github.com/Knuckles-Team/agent-terminal-ui).

## License

Agent Terminal UI is released under the [MIT License](agent_terminal_ui/LICENSE).
