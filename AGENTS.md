# Agent Terminal UI

## What this repository owns

Agent Terminal UI is a Textual terminal frontend for interactive and headless agent sessions. It owns terminal presentation, local session interaction, capability forms, run inspection, and its client-side protocol adapters. It does not own agent execution, the governed gateway, or durable graph storage.

## Architecture and module map

Graph OS provides the REST gateway for capability discovery and invocation, run inspection, and dashboard data. Agent Utilities owns agent execution and control-plane behavior. Epistemic Graph owns durable graph data and reasoning.

The main chat client uses this repository's HTTP/SSE implementation of an ACP-style JSON-RPC transport. The current Graph OS deployment does not mount that chat endpoint; a compatible service must be configured through `ACP_URL`. The client does not use Zed's ACP SDK.

- `agent_terminal_ui/terminal_ui.py` provides the CLI and selects interactive or headless execution.
- `agent_terminal_ui/client.py` owns Graph OS REST methods and the chat transport.
- `agent_terminal_ui/screens/` and `agent_terminal_ui/widgets/` implement the Textual interface.
- `agent_terminal_ui/headless.py` runs sessions without the interactive widget tree.
- `tests/` contains automated tests, including import-boundary checks.
- `docs/` contains configuration, architecture, and operator documentation.

## Commands

Use Python 3.11 through 3.14.

```bash
uv sync --extra test
uv run agent-terminal-ui
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
mkdocs build --strict
```

## Quality gates

Run `pre-commit run --all-files` before committing. Run the test suite and strict documentation build when changing application behavior or public documentation. Keep the frontend import boundary free of agent-framework and training-library imports.

## Development rules

- Keep platform HTTP behavior behind `AgentClient` and model responses explicitly.
- Keep chat availability distinct from Graph OS REST availability.
- Do not claim Graph OS provides the ACP-style chat endpoint unless the deployment exposes it.
- Keep docs concise and factual; use present-tense architecture and display names.
- Add focused tests for behavior changes and keep generated build output out of commits.

## Documentation

The [README](README.md) is the package entry point. The [documentation home](docs/index.md) links to [capabilities](docs/capabilities.md), [interfaces](docs/interfaces.md), [architecture](docs/architecture.md), [configuration](docs/configuration.md), and [status](docs/status.md). The five platform references are [Epistemic Graph](https://knuckles-team.github.io/epistemic-graph/), [Agent Utilities](https://knuckles-team.github.io/agent-utilities/), [Graph OS](https://knuckles-team.github.io/graph-os/), [Agent Connector SDK](https://knuckles-team.github.io/agent-connector-sdk/), and [Agent Web UI](https://knuckles-team.github.io/agent-webui/).

## Branching & isolation

Use a focused branch and commit only reviewed files for the task. Check `git status` and the staged diff before committing. Keep credentials, caches, build output, logs, and scratch files out of version control. Preserve unrelated operator changes in shared checkouts.
