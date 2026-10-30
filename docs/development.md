# Develop tuig

The only runtime is Rust/Ratatui in `native/tuig`. Python is
used for repository validation and native PTY tests, not as a frontend.

Read `AGENTS.md` and the owning requirement in `specs/terminal-runtime` before
editing. Keep Arbora responsible for authorization, task lifecycle and served
operations. Do not add a local model, tool executor or compatibility frontend.

Run Cargo format, test and Clippy checks with the locked manifest. Run the
Python native PTY harness against the same compiled executable through
`TUI_NATIVE_TEST_BINARY`. Record focused results separately from live-service,
full parity and release qualification. Do not publish without authorization.
