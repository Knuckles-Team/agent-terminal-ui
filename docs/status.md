# Status

The native client supports unary task submission and observation, public task
output, themes, viewport controls, run inspection and host logs. Headless mode
uses the same client and fails closed on input/authentication requirements.

Interactive composition, streaming, approval attachment, context continuation
and durable resume remain open. Full served parity and release performance are
not established by focused tests. The Python implementation is removed, not a
fallback. See the canonical [requirements](../specs/terminal-runtime/requirements.md).

An experimental explicit local ACP v1 path supports headless one-shot text
through an internal Arbora child process. It advertises no host tools or
permission grants. Its scripted and SDK transport checks are not proof of
installed Arbora/AU pairing, interactive ACP or durable history. These remain
open under `TUI-RUNTIME-R011.14` and the existing coding-session requirements.
