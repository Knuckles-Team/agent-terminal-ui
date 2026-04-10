<h1 align="center">
    agent-terminal-ui
</h1>
<p align="center">
    <p align="center">Terminal user interface for AI agents built on <a href="https://github.com/DavidKoleczek/agent-core">agent-core</a>.</p>
</p>
<p align="center">
    <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"></a>
    <a href="https://github.com/astral-sh/ty"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json" alt="ty"></a>
    <a href="https://pypi.org/project/agent-terminal-ui/"><img src="https://img.shields.io/pypi/v/agent-terminal-ui" alt="PyPI"></a>
    <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

A [Textual](https://textual.textualize.io/)-based terminal interface for interacting with AI agents. Built on [agent-core](https://github.com/DavidKoleczek/agent-core) and [InteropRouter](https://github.com/DavidKoleczek/interop-router) for unified model provider support.

> [!NOTE]
> This library is in early development and subject to change.


## Usage

Ensure `OPENAI_API_KEY` is set in your environment.

Run directly from PyPI:

```bash
uvx agent-terminal-ui
```

Or if installed locally:

```bash
uv run agent-terminal-ui
```

Or run directly with Textual:

```bash
uv run textual run src.agent_tui.app:AgentApp
```


## Development

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [prek](https://github.com/j178/prek/blob/master/README.md#installation)

### Setup

Create uv virtual environment and install dependencies:

```bash
uv sync --frozen --all-groups
```

Set up git hooks:

```bash
prek install
```

To update dependencies (updates the lock file):

```bash
uv sync --all-groups
```

Run formatting, linting, and type checking:

```bash
uv run ruff format && uv run ruff check --fix && uv run ty check
```
