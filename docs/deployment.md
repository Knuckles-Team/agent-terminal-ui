# Deployment

The release workflow publishes Python packages to PyPI on version tags or manual dispatch.
An ordinary push to main does not publish a package.
See [.github/workflows/release.yml](../.github/workflows/release.yml).
The documentation publishes through [.github/workflows/pages.yml](../.github/workflows/pages.yml).

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
