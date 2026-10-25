# Project Constitution: agent-terminal-ui

## Mission

Deliver `tuig`, one Rust/Ratatui terminal frontend for Arbora. PyPI distributes
the native executable; Python may support developer validation but must not
provide a runtime UI, compatibility frontend or launcher.

## Boundaries

The frontend owns terminal presentation and operator input. Arbora owns served
task lifecycle, authentication, authorization and operations. Agent runtime and
graph decisions stay upstream. Never implement a second agent or tool executor.

Current transport is Arbora A2A and served HTTP operations. A planned protocol
is not an implemented endpoint. Approval fails closed when unavailable. Unknown
mutation outcomes are never automatically replayed. Preserve distinct opaque
task, context and run identities across observations.

## Engineering

Canonical requirements and retained parity gaps live in `specs/terminal-runtime`.
Retiring an implementation does not mark its product requirements verified.
Use Rust tests for runtime behavior and Python only for developer/PTY harnesses.
Run formatting, native tests, Clippy and repository pre-commit checks. Disclose
unrun or blocked checks; never bypass them or treat fixture tests as served proof.

## Presentation

Keep keyboard access, responsive asynchronous I/O, dynamic themes, no-color
support and bounded views. Remote cancellation requires explicit confirmation.
Native composition, streaming, approval attachment and durable resume remain
open until their existing acceptance criteria are met.
