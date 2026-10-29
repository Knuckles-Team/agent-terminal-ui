# Status

The native client supports unary task submission and observation, public task
output, themes, viewport controls, run inspection and host logs. Headless mode
uses the same client and fails closed on input/authentication requirements.

One-task interactive A2A composition is available. Streaming, approval
attachment, context continuation and durable resume remain open. Full served parity and release performance are
not established by focused tests. The Python implementation is removed, not a
fallback. See the canonical [requirements](../specs/terminal-runtime/requirements.md).

An explicit local ACP v1 path supports interactive text sessions and headless
one-shot text through an internal Arbora child process. It advertises no host tools or
permission grants. Its scripted and SDK transport checks are not proof of
a released Arbora/AU pairing or durable history. These remain
open under `TUIG-RUNTIME-R011.14` and the existing coding-session requirements.
