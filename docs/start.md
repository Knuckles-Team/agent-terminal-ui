# Start

Install the package, then run the terminal app.

```bash
pip install agent-terminal-ui
agent-terminal-ui
```

The Python app uses GraphOS A2A chat and REST operations. The Configuration page lists the settings. The Features page lists the slash commands.

To work on the repository, clone it and run `uv run --frozen pytest tests -q`.

## Native read-only preview

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

Press r to refresh the same read, c to cancel the local request, or q or Ctrl+C
to exit. Local cancellation does not cancel a remote task. This preview does not
submit tasks, stream responses or approve actions. Keep Python and OpenCode for
existing workflows.
