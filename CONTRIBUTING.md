# Contributing

Read [AGENTS.md](AGENTS.md) and the owning runtime requirement before editing.
Use a separate Git worktree and stage explicit paths.

## Setup and checks

Rust implements the runtime. Python supports repository and native PTY tests.

```sh
uv sync --frozen --no-install-project --group test
uv run --frozen --no-sync pytest tests -q
cargo fmt --manifest-path native/tuig/Cargo.toml --check
cargo test --locked --manifest-path native/tuig/Cargo.toml
cargo clippy --locked --manifest-path native/tuig/Cargo.toml --all-targets -- -D warnings
uvx --from pre-commit==4.6.2 pre-commit run --all-files
```

Set `TUI_NATIVE_TEST_BINARY` to the compiled `tuig` executable for native PTY
checks. A run that skips those tests is not native integration qualification.
Use the native-wheel workflow to validate installed binary provenance and the
command with Python and Cargo absent from its runtime PATH.

## Source map

| Path | Responsibility |
| --- | --- |
| `native/tuig/src/main.rs` | Native command dispatch and terminal loop. |
| `native/tuig/src/cli.rs` | Headless flag selection. |
| `native/tuig/src/headless.rs` | Unary headless observation. |
| `native/tuig/src/lib.rs` | Authenticated Arbora task client. |
| `native/tuig/tests/` | Native protocol and presentation tests. |
| `tests/` | Developer checks and compiled-native PTY harnesses. |
| `specs/terminal-runtime/` | Requirements, retained gaps and generated status. |

## Evidence and publication

Generate canonical status with the shared spec generator. Deleted Python test
bindings must not count as native acceptance. Historical landing commits remain
historical evidence, not a passing native journey. Preserve open composer,
streaming, approval, continuation, durability and ACP requirements.

Publish migration work as a draft until native tests, installed-wheel checks,
PTY journeys and required repository gates pass. A release or deployment needs
separate authorization. Do not claim skipped or unrun checks passed.
