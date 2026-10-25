# TUI-RUNTIME — Terminal Arbora operation client

**Owner:** agent-terminal-ui

**Delivery:** specified; implementation and acceptance require separate evidence.

**Requirement:** TUI-RUNTIME-R001 (terminal-client share of the Arbora command and A2A interface). See [`requirements.md`](requirements.md) for the full definition of every requirement ID this spec owns and [`status.json`](status.json) for their current delivery and acceptance state.
**Related public owners:** [Arbora hosted operation service](https://github.com/Knuckles-Team/arbora/tree/main/specs/hosted-api-operations) supplies the operation registry, generated client and authorization boundary. Its [A2A task projection](https://github.com/Knuckles-Team/arbora/tree/main/specs/a2a-task-projection) supplies task methods. GeniusBot owns its own consumer implementation. This spec states the shared wire contract but does not assign its code to the TUI.

## Purpose and user stories

1. As an operator, I can discover a versioned operation, inspect its schema, and invoke it through the same authenticated Arbora service used by the conversation. I see the returned result or a stable, actionable error.
2. As an operator, I can preview a side effect and explicitly confirm the exact server-issued PLAN, with its operation, parameters, identity, registry version and expiry bound to the confirmation. A changed or expired plan is rejected before an effect.
3. As a Python 3.11 TUI user without a compatible generated client, I can continue basic A2A chat; an operation command clearly reports client unavailability.
4. As an operator awaiting approval, I cannot use a local shortcut to turn an unserved or unverified A2A approval into a grant. Approval remains disabled until the Arbora approval contract and served identity proof exist.

## Functional requirements

| ID | Requirement | Acceptance evidence |
|---|---|---|
| TUI-RUNTIME-R001.1 | `/op <op-id> <JSON object>` validates the operation with the installed generated registry and invokes the versioned Arbora endpoint. It rejects unknown IDs, malformed JSON, non-object input, and registry digest mismatch. | Command/client tests and installed-wheel contract test |
| TUI-RUNTIME-R001.2 | The TUI transports the caller's verified credential to Arbora over TLS for remote endpoints. It never fabricates a principal, persists a bearer in a conversation, or logs it. Missing credential and insecure remote endpoint fail closed. | Negative credential and transport tests |
| TUI-RUNTIME-R001.3 | A side-effect PLAN is display-only until `/confirm <plan_ref>` sends the exact server-issued binding through `arbora.plan/confirm`; references are single use. A changed operation, parameters, digest, subject, or expired reference cannot run. | A2A contract, tamper, replay and expiry tests |
| TUI-RUNTIME-R001.4 | The client parses the documented Arbora error envelope and handles timeout, network failure, malformed response and non-success status without suggesting success. Chat remains usable after an operation failure. | Mock transport and TUI flow tests |
| TUI-RUNTIME-R001.5 | An A2A `input-required` approval is surfaced as pending, not silently granted. Approval action methods stay unavailable until a signed, pending-call-bound exchange has a public Arbora contract and served end-to-end proof. | Negative approval tests, later served identity receipt |
| TUI-RUNTIME-R001.6 | Python 3.11 base installation remains usable without an Arbora generated client. The operation feature is explicitly unavailable until a compatible optional client is installed. Dependency metadata and lock reflect the supported Python range. | Clean 3.11 install and command smoke |
| TUI-RUNTIME-R001.7 | Existing `/capabilities`, `/run`, and conversation entry points either use the corresponding public Arbora contracts or are clearly identified as legacy read-only paths during migration. No new AU knowledge-graph internals are imported. | Import and route inventory; UI regression tests |

## Scenarios and failure behavior

- Given an authenticated Arbora service and a compatible registry, `/op <registered-id> {"key":"value"}` sends one typed invocation and renders its result without opening a second in-process gateway.
- Given a PLAN response, `/confirm` displays the bound action and asks the server to confirm only that plan. A second confirmation, a different caller or a changed digest is refused.
- Given Python 3.11 without a compatible operation client, `/op` explains the unavailable feature while an ordinary chat turn still works.
- Given an `input-required` approval, the TUI displays pending state; an attempted approval action returns `APPROVAL_UNAVAILABLE` until the separate approval authority is proven.
- Given an HTTP error, invalid envelope, failed TLS check, or disconnected server, the TUI presents a failure and preserves the current session.

## Success and scope

Success requires the positive and negative scenarios above, installed-client compatibility, a served Arbora operation round trip, and a separate served approval identity/WorkItem receipt before approval actions can be enabled. A source commit or unit-test pass alone is not acceptance. The TUI does not own Arbora authorization, registry generation, EG persistence, or the GeniusBot implementation.

## Traceability

Current delivery and acceptance state for each requirement ID above is recorded in [`status.json`](status.json), not here.

| Local ownership | Other owner contract |
|---|---|
| This TUI's commands, transport, presentation and Python packaging (`TUI-RUNTIME-R001`) | Arbora's generated operation client, versioned HTTP envelope and A2A methods (see links above). GeniusBot implements its own consumer |
| Displaying and safely refusing or resuming an approval only after contract proof | Arbora's signed A2A approval and durable human identity authority (see the A2A task projection link above), proven end to end before approval actions are enabled |

## Run observation

`TUI-RUNTIME-R010` and its inspection children define the read-only run surface.
The owning requirements, plan and test specification define its producer dependencies and acceptance.
The surface must distinguish unavailable values from measured zero and aggregate values from per-run values.

<!-- spec-definition-patch:r002-consumer-spec -->
## TUI-RUNTIME-R002 consumer slice

R002 stays intact. It keeps the full original chat transport requirement. Child R002.1 repeats that acceptance in the rollup. Children .2 through .6 define the host receipt and log consumer. Arbora owns host startup, interface selection, authority, scope checks, redacted log production and host lifetime. The terminal consumes a versioned HostLaunchReceipt and its opaque authorized log reference. Local paths, strings and environment values never grant access.

Arbora producer contracts R009.2 through R009.6 and R010.7 are prerequisites. R010.7 puts web_logs in HostLaunchRequest, but the current HostLaunchReceipt v1 contract omits that field. Arbora must bind the effective preference into the authenticated receipt or handoff, scoped to host, workspace, tenant and principal. Until Arbora supplies it, the TUI makes zero log reads. The required host redacted sink remains enabled. This definition does not claim current producer exports. It leaves TUI-RUNTIME-R010 and its run-inspector obligations intact.

AU:116 source SHA-256 08a22602bd677e4fc39260d058503fa73a2216ad40bbe817c17d3bef256722ef. Map its remaining consumer obligation to R002.2, .3, .5 and .6 after the producer clauses.
AU:117 source SHA-256 fddbc1b35588be4427396a7aa827414d9d7bba01a8837f905a8b1c9b1eac4694. Map its remaining mode and unified-view obligation to R002.2 through .6, especially .4. Child .1 preserves the original chat transport acceptance. These mappings claim no runtime delivery.
<!-- /spec-definition-patch -->

## Rust migration scope

The dated migration amendment in plan.md extends R002 transport ownership and
R008 presentation to Rust with asynchronous execution. It preserves R001 authorization
and R010 run identity. The terminal remains a thin client; Arbora owns runtime
and policy, and EG owns graph and reasoning. A broker requires measured benefit
and may retain only principal-scoped authorized views. Success requires the
served protocol, failure and performance acceptance in test-spec.md. Definitions
and local tests alone do not establish runtime verification.

R002.7 adds only configured native discovery and its local request lifecycle.
It must not imply streaming, remote task cancellation or approval readiness.
The Python client and the incumbent coding terminal remain available during this slice.

R002.1.1 adds the native task correlation model. Server task and context IDs are
required; the server run ID is optional and never inferred. The model validates
subsequent events against the initial binding. This child enables no transport
actions and does not close served streaming or cutover acceptance.

## One-shot tool task

TUI-RUNTIME-R002.8 and its children define one governed background tool-task command.
An operator must see task identity, lifecycle, output, approval requests and termination through one terminal invocation.
The terminal must preserve Arbora authority and must not run the tool locally.
A server-attested matching preapproval may suppress a permission prompt; a local flag supplies no authority.
Unavailable producer contracts must leave this mode unavailable without removing existing chat or discovery behavior.
Success requires the served CLI acceptance and exact producer bindings in plan.md.

## Nested execution explorer

R010.11 through R010.14 extend read-only run inspection to nested execution and dependency navigation.
R012.7 through R012.9 add separate, capability-gated child messaging and completed-child continuation.
Existing public-summary and tool-fold acceptance remains unchanged.
A graph selection supplies no execution authority and does not change the active chat target.
Arbora owns served identity, authorization and control bindings; Agent Utilities owns run mechanics.
The terminal must not schedule agents, reconstruct lineage or expose private reasoning.

## Edit a prompt and keep both conversations

TUI-RUNTIME-R012.10 adds discoverable selection and editing of an earlier own
user message in the Rust/Ratatui terminal, `tuig`. A boundary preview explains which
completed context survives and which replies are excluded. The original stays
intact; the edited prompt starts a new persisted branch with a return path.
Forking neither undoes nor replays earlier external actions.

The same Arbora contract serves WebUI and the native terminal. Task-output browsing,
local transcript copies and completed-child continuation cannot stand in for
that contract. The new rows remain SPECIFIED until producer and installed
client proof passes. Existing complete-history and resume gaps remain open.
