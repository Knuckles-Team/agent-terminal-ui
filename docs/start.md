# Start

Install the package, then run the terminal app.

```bash
pip install agent-terminal-ui
agent-terminal-ui
```

The Python app uses Arbora A2A chat and REST operations. The Configuration page lists the settings. The Features page lists the slash commands.

To work on the repository, clone it and run `uv run --frozen pytest tests -q`.

## Native preview

The native client reads AGENT_URL and AGENT_BEARER_TOKEN from its process
environment. The default endpoint is http://localhost:8000. Remote endpoints
require HTTPS and a caller credential. Do not put credentials in command history.

```bash
CARGO_BUILD_JOBS=2 cargo run --locked --manifest-path native/agent-terminal-ui/Cargo.toml
```

By default, the preview reads the Arbora Agent Card. Set AGENT_TASK_ID to an
existing task ID to read its acknowledged state and separate task, context and
run IDs. A missing run ID is shown as unavailable. An empty task ID fails before
any request. A failed refresh clears the previously displayed task values.

Use --prompt to submit one ordinary text task with a caller credential:

```bash
CARGO_BUILD_JOBS=2 cargo run --locked --manifest-path native/agent-terminal-ui/Cargo.toml -- --prompt "Describe the current task"
```

Do not combine --prompt with AGENT_TASK_ID. A valid acknowledgement selects the
returned task for refresh and cancellation. The client sends once. An interrupted
submission has an unknown outcome and cannot be refreshed without its task ID.
Refresh never submits the prompt again.

Press r to refresh, c to stop waiting, or q or Ctrl+C to exit.
After a successful read of an active task, press x, then y to confirm
remote cancellation. Press n or Escape to dismiss the confirmation. Cancellation
succeeds only after Arbora returns the same bound task in the canceled state.

An interrupted or failed cancellation has an unknown outcome. Press r to read
the task state before trying again. Stopping the local wait cannot undo a remote
cancellation. The client never retries cancellation automatically. This preview
does not stream responses or approve actions. Keep Python and
OpenCode for existing workflows.

## Observe an existing task

Run `agent-terminal-ui --observe-task TASK_ID` with the usual `AGENT_URL` and
`AGENT_BEARER_TOKEN` settings. This reads the task until it ends or needs input.
It never submits, approves or cancels a task. Ctrl+C detaches locally.
Missing output and terminal reason remain unavailable. This mode polls snapshots;
it does not replay streamed output or resume a lost event cursor.
