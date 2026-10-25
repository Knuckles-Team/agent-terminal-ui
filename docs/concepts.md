# Concept Registry — agent-terminal-ui

> **Prefix**: `CONCEPT:TUI-*`
> **Version**: 2.3.2
> **Bridge**: [`CONCEPT:AU-ECO.messaging.native-backend-abstraction`](https://github.com/Knuckles-Team/agent-utilities/blob/main/docs/concepts.md) (Unified Toolkit Ingestion)

---

## Runtime ownership

`tuig` is a frontend client, not an MCP or A2A server. It consumes Arbora task
and operation contracts. Backend orchestration and knowledge decisions remain
upstream. Historical Python concept descriptions remain in git history.

## Native terms

**tuig:** the sole native Rust/Ratatui command.

**Arbora:** the served task and operations authority.

**A2A:** the currently implemented task transport.

**ACP:** Agent Client Protocol; the experimental local headless path uses it
for one text turn through an owned backend child. Installed-backend and full
protocol acceptance remain open.

**Headless:** native unary observation without a terminal renderer.

See the [ecosystem glossary](glossary.md) for shared terms. The shared Pages theme
owns that generated glossary; keep native terms on this page.
