# Start

Install the package, then run the terminal app.

```bash
pip install agent-terminal-ui
agent-terminal-ui
```

The Python app uses GraphOS A2A chat and REST operations. The Configuration page lists the settings. The Features page lists the slash commands.

To work on the repository, clone it and run `uv run --frozen pytest tests -q`.

## Native preview

The native client reads AGENT_URL and AGENT_BEARER_TOKEN from its process
environment. The default endpoint is http://localhost:8000. Remote endpoints
require HTTPS and a caller credential. Do not put credentials in command history.

```bash
CARGO_BUILD_JOBS=2 cargo run --locked --manifest-path native/agent-terminal-ui/Cargo.toml
```

By default, the preview reads the GraphOS Agent Card. Set AGENT_TASK_ID to an
existing task ID to read its acknowledged state and separate task, context and
run IDs. A missing run ID is shown as unavailable. An empty task ID fails before
any request. A failed refresh clears the previously displayed task values.

Press r to refresh, c to stop waiting, or q or Ctrl+C to exit.
After a successful read of an active task, press x, then y to confirm
remote cancellation. Press n or Escape to dismiss the confirmation. Cancellation
succeeds only after GraphOS returns the same bound task in the canceled state.

An interrupted or failed cancellation has an unknown outcome. Press r to read
the task state before trying again. Stopping the local wait cannot undo a remote
cancellation. The client never retries cancellation automatically. This preview
does not submit tasks, stream responses or approve actions. Keep Python and
OpenCode for existing workflows.
