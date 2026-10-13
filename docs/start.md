# Start

Install the package, then run the terminal app.

```bash
pip install agent-terminal-ui
agent-terminal-ui
```

The Python app uses GraphOS A2A chat and REST operations. The Configuration page lists the settings. The Features page lists the slash commands.

To work on the repository, clone it and run `uv run --frozen pytest tests -q`.

## Native discovery preview

The native client reads AGENT_URL and AGENT_BEARER_TOKEN from its process
environment. The default endpoint is http://localhost:8000. Remote endpoints
require HTTPS and a caller credential. Do not put credentials in command history.

```bash
CARGO_BUILD_JOBS=2 cargo run --locked --manifest-path native/agent-terminal-ui/Cargo.toml
```

This preview reads the GraphOS Agent Card. It does not submit tasks or approvals.
Press c to cancel local discovery, r to retry, or q to exit. Local cancellation
is not remote task cancellation. Keep Python and OpenCode for existing workflows.
