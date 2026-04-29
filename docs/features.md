# Features

## Slash Commands

Registered in `commands.py` via the `self.commands` dict. Current registry: 31 commands plus 2 aliases.

**Implemented**: `/help`, `/clear`, `/exit` (alias `/quit`), `/mcp`, `/history`, `/image`, `/plan`, `/chat`, `/build`, `/init`, `/review`, `/test`, `/search`, `/stats` (alias `/cost`), `/model`, `/theme`, `/queue`, `/queue:clear`, `/queue:toggle`, `/compact`, `/context`, `/diff`, `/recap`, `/export`, `/focus`, `/fast`, `/keybindings`, `/memory`, `/agents`, `/simplify`, `/add-dir`.

### `/model` command

The `/model` command is backed by the `agent-utilities` multi-model registry
(`GET /models`):

- `/model` or `/model list` -- render the configured models in a Rich table
  (id, name, provider, tier, tags, default marker, per-1M cost).
- `/model show` -- show a Panel with full metadata for the currently active
  model (falls back to the registry default when no override is set).
- `/model set <id>` -- pick a model id for subsequent turns. The chosen id
  is stored on both `app._current_model_id` and `app._current_model`, and
  the `AgentClient` propagates it as an `x-agent-model-id` header so the
  backend can override the registry default for the session.

Zero-cost / local models (`cost: {input: 0, output: 0}`) render as
`$0.00 / $0.00` in the table rather than `-`, so tokens and tool counts
remain visible even when the model itself is free.

**Removed** (nine stub commands with no working implementation): `/effort`, `/permissions`, `/color`, `/hooks`, `/branch` / `/fork`, `/copy`, `/undo` / `/rewind`, `/loop` / `/proactive`, `/btw`. Removing them keeps the slash menu aligned with the actual supported feature set.

Note: `/mcp`, `/history`, and `/export` are still listed as implemented but currently raise `AttributeError` at runtime due to missing `AgentClient` methods (see [Known Issues](agents.md#known-issues)).

## Keyboard Shortcuts

Claude-code parity bindings are wired in `agent_terminal_ui/app.py::BINDINGS`. Summary of the current mapping:

| Binding | Action |
|---|---|
| `Ctrl+L` | Clear log |
| `Ctrl+O` | Toggle sidebar |
| `Ctrl+T` | Toggle sidebar (aliased to `Ctrl+O` so both work) |
| `Ctrl+R` | Reverse search |
| `Ctrl+U` / `Ctrl+Y` | Clear / restore input |
| `Ctrl+H` | Show help |
| `Ctrl+G` | Open in editor |
| `Ctrl+B` | Background tasks |
| `Alt+P` | Model picker |
| `Alt+T` | Toggle extended thinking |
| `Alt+O` | Toggle fast mode |
| `Alt+Shift+T` | Switch theme (moved off `Ctrl+T`, which is now the sidebar alias) |
| `Shift+Tab` | Cycle mode |
| `Esc Esc` | Rewind |
| `!` (input prefix) | Direct bash execution |

**Planned (not yet implemented)**: `@` file-mention autocomplete prefix.
