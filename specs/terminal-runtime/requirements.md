# TUI-RUNTIME-001 requirements

Every requirement this specification owns, with the proof that closes it. Delivery state and
public evidence for each ID are recorded in [`status.json`](status.json); this file defines what
each ID means. The design is in [`spec.md`](spec.md) and [`plan.md`](plan.md), the test contract
in [`test-spec.md`](test-spec.md), and the work order in [`tasks.md`](tasks.md).

| ID | Requirement | Verification |
|---|---|---|
| `TUI-RUNTIME-R001` | **Terminal operation client issues typed commands with pending approvals.** Agent-terminal-ui's client and commands modules validate an operation ID and JSON input against the installed generated Graph OS registry before invoking it, and surface an A2A approval exchange as pending rather than granting it locally; approval actions stay unavailable until the corresponding Graph OS contract is proven end to end. | Command and client unit tests plus negative approval tests confirm invalid operations are rejected and pending approvals are never silently granted. |
| `TUI-RUNTIME-R002` | **Terminal chat transport is reconciled with the current Graph OS boundary.** Agent-terminal-ui selects and implements one canonical transport for its primary conversational connection to Graph OS in place of the unmounted streaming and remote-procedure routes it currently expects, updates its client to that transport atomically, and removes the superseded code path. | Session, authentication, streaming and cancel behavior against the chosen transport are proven by integration tests before the superseded path is removed. |
