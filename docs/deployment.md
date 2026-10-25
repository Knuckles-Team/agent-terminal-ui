# Deployment

The release workflow publishes Python packages to PyPI on version tags or manual dispatch.
An ordinary push to main does not publish a package.
See [.github/workflows/release.yml](https://github.com/Knuckles-Team/agent-terminal-ui/blob/main/.github/workflows/release.yml).
The documentation publishes through [.github/workflows/pages.yml](https://github.com/Knuckles-Team/agent-terminal-ui/blob/main/.github/workflows/pages.yml).

The `Dockerfile` builds a two-stage image on `python:3.14-slim`. Its entry point is `agent-terminal-ui`.


## Native terminal

The Rust crate declares its version in Cargo.toml and sets `publish = false`.
It needs a Rust toolchain.
From the repository root, run:

```bash
cargo run --locked --manifest-path native/agent-terminal-ui/Cargo.toml
```

Configure `AGENT_URL` and an existing `AGENT_BEARER_TOKEN` for the default bearer mode.
For anonymous loopback only, set `AGENT_AUTH_MODE=none` and unset the bearer token.
The Arbora server must also permit that anonymous mode.
This executable does not use the Python CLI flags. Native live-service parity
and release performance qualification remain open.

With a validated task run binding, press `i` to open the read-only inspector.
Inside the inspector, `g` switches between summary and flat execution graph.
Graph reads require the separately advertised `runs.execution_graph` operation;
an unavailable summary does not prevent them. Tab and Shift+Tab select a step.
The details distinguish predecessors from dependents and show public event
references. Use PageUp/PageDown or Home/End to scroll and Ctrl+F to search.
Press `r` to refresh, `c` to cancel the local read and Escape to close.

The v1 graph has complete flat topology but only an observed lifecycle prefix.
Unobserved steps have unknown state. Spawned-child navigation, transcripts,
child messaging and continuation remain unavailable. This source-only extension
still needs native build and compiled-terminal qualification.
