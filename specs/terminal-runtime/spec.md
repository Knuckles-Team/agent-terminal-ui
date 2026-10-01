# TUI-RUNTIME-001: Terminal GraphOS operation client

**Owner:** agent-terminal-ui

**Delivery:** specified; implementation and acceptance require separate evidence.

**Requirement:** TUI-RUNTIME-R001 (terminal-client share of the GraphOS command and A2A interface). See [`requirements.md`](requirements.md) for the full definition of every requirement ID this spec owns and [`status.json`](status.json) for their current delivery and acceptance state.
**Related public owners:** [GraphOS hosted operation service](https://github.com/Knuckles-Team/graph-os/tree/main/specs/hosted-api-operations) supplies the operation registry, generated client and authorization boundary; its [A2A task projection](https://github.com/Knuckles-Team/graph-os/tree/main/specs/a2a-task-projection) supplies task methods. GeniusBot owns its own consumer implementation; this spec states the shared wire contract but does not assign its code to the TUI.

## Purpose and user stories

1. As an operator, I can discover a versioned operation, inspect its schema, and invoke it through the same authenticated GraphOS service used by the conversation. I see the returned result or a stable, actionable error.
2. As an operator, I can preview a side effect and explicitly confirm the exact server-issued PLAN, with its operation, parameters, identity, registry version and expiry bound to the confirmation. A changed or expired plan is rejected before an effect.
3. As a Python 3.11 TUI user without a compatible generated client, I can continue basic A2A chat; an operation command clearly reports client unavailability.
4. As an operator awaiting approval, I cannot use a local shortcut to turn an unserved or unverified A2A approval into a grant. Approval remains disabled until the GraphOS approval contract and served identity proof exist.

## Functional requirements

| ID | Requirement | Acceptance evidence |
|---|---|---|
| TUI-RUNTIME-R001.1 | `/op <op-id> <JSON object>` validates the operation with the installed generated registry and invokes the versioned GraphOS endpoint. It rejects unknown IDs, malformed JSON, non-object input, and registry digest mismatch. | Command/client tests and installed-wheel contract test |
| TUI-RUNTIME-R001.2 | The TUI transports the caller's verified credential to GraphOS over TLS for remote endpoints. It never fabricates a principal, persists a bearer in a conversation, or logs it. Missing credential and insecure remote endpoint fail closed. | Negative credential and transport tests |
| TUI-RUNTIME-R001.3 | A side-effect PLAN is display-only until `/confirm <plan_ref>` sends the exact server-issued binding through `graphos.plan/confirm`; references are single use. A changed operation, parameters, digest, subject, or expired reference cannot execute. | A2A contract, tamper, replay and expiry tests |
| TUI-RUNTIME-R001.4 | The client parses the documented GraphOS error envelope and handles timeout, network failure, malformed response and non-success status without suggesting success. Chat remains usable after an operation failure. | Mock transport and TUI flow tests |
| TUI-RUNTIME-R001.5 | An A2A `input-required` approval is surfaced as pending, not silently granted. Approval action methods stay unavailable until a signed, pending-call-bound exchange has a public GraphOS contract and served end-to-end proof. | Negative approval tests, later served identity receipt |
| TUI-RUNTIME-R001.6 | Python 3.11 base installation remains usable without a GraphOS generated client; the operation feature is explicitly unavailable until a compatible optional client is installed. Dependency metadata and lock reflect the supported Python range. | Clean 3.11 install and command smoke |
| TUI-RUNTIME-R001.7 | Existing `/capabilities`, `/run`, and conversation entry points either use the corresponding public GraphOS contracts or are clearly identified as legacy read-only paths during migration. No new AU knowledge-graph internals are imported. | Import and route inventory; UI regression tests |

## Scenarios and failure behavior

- Given an authenticated GraphOS service and a compatible registry, `/op <registered-id> {"key":"value"}` sends one typed invocation and renders its result without opening a second in-process gateway.
- Given a PLAN response, `/confirm` displays the bound action and asks the server to confirm only that plan. A second confirmation, a different caller or a changed digest is refused.
- Given Python 3.11 without a compatible operation client, `/op` explains the unavailable feature while an ordinary chat turn still works.
- Given an `input-required` approval, the TUI displays pending state; an attempted approval action returns `APPROVAL_UNAVAILABLE` until the separate approval authority is proven.
- Given an HTTP error, invalid envelope, failed TLS check, or disconnected server, the TUI presents a failure and preserves the current session.

## Success and scope

Success requires the positive and negative scenarios above, installed-client compatibility, a served GraphOS operation round trip, and a separate served approval identity/WorkItem receipt before approval actions can be enabled. A source commit or unit-test pass alone is not acceptance. The TUI does not own GraphOS authorization, registry generation, EG persistence, or the GeniusBot implementation.

## Traceability

Current delivery and acceptance state for each requirement ID above is recorded in [`status.json`](status.json), not here.

| Local ownership | Other owner contract |
|---|---|
| This TUI's commands, transport, presentation and Python packaging (`TUI-RUNTIME-R001`) | GraphOS's generated operation client, versioned HTTP envelope and A2A methods (see links above); GeniusBot implements its own consumer |
| Displaying and safely refusing or resuming an approval only after contract proof | GraphOS's signed A2A approval and durable human identity authority (see the A2A task projection link above), proven end to end before approval actions are enabled |
