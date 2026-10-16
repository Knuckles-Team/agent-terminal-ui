# TUI-RUNTIME design and integration plan

## Existing wiring and architecture

At the current public main revision, `CommandProcessor` in `agent_terminal_ui/commands.py` owns slash-command dispatch and the `/capabilities` and `/run` commands. `AgentClient` in `agent_terminal_ui/client.py` owns HTTP transport, session events and the older `/api/capabilities/*` and `/api/runs/*` routes. `agent_terminal_ui/app.py`, `screens/main.py`, `tui/input_text_area.py`, `tui/capability_palette.py` and `tui/run_inspector.py` are presentation consumers. This is the path to extend; no parallel command router, HTTP client or local GraphOS gateway should be created.

At main 5ac5e3fec4d590f167d2c6bd694683dbd8950c26, the TUI-RUNTIME-R001 client implementation is present. Its unit tests do not establish served acceptance. It implements `/op`, `/confirm`, a lazy generated-client import and fail-closed approval behavior. Review and compose its exact changes rather than rebuilding the same transport from scratch. The current main package targets Python `>=3.11,<3.15`; GraphOS generated-client compatibility must be handled without raising that base floor silently.

```text
keyboard / slash command
    -> CommandProcessor
    -> AgentClient (one session, caller credential, HTTP/A2A transport)
    -> GraphOS versioned operation API or A2A plan confirmation
    -> server authorization, registry and effect gate
    -> typed result/error -> existing conversation and run widgets
```

## Contracts and decisions

| Boundary | Contract to implement or verify |
|---|---|
| Command input | `/op <registered-id> <JSON object>`; JSON is parsed once; a malformed or absent object is refused before any network call. `/confirm <opaque-plan-ref>` never accepts a caller-supplied substitute operation or parameters. |
| Generated operation client | Resolve `schema_for(op)` and `invoke(transport, op, params)` lazily. The installed registry digest must match the server. Missing package data or incompatible runtime yields `CLIENT_UNAVAILABLE`, not a fallback to an untyped endpoint. |
| HTTP operation | Use GraphOS's public versioned operation endpoint, caller-scoped authorization header, structured result and stable error envelope. No direct import of graph-os server internals or AU knowledge-graph internals. |
| A2A conversation | Reuse the GraphOS Agent Card and authenticated JSON-RPC task flow. Keep session/task identity on streaming and resumed turns; network errors must leave the UI responsive. |
| PLAN | Store only the short-lived server binding necessary for display and one confirmation. Bind to exact plan reference, op, input digest, caller/session, registry digest and expiry. The server makes the final authoritative check. Clear after use or failure. |
| Approval | An `input-required` task is a pending request. Signed approval must be bound to the pending call and human authority in GraphOS. Until that public contract and served proof are present, refuse `approvals.*` and direct fleet-grant shortcuts. |
| Security | Require TLS and a verified credential for remote GraphOS. Do not emit bearer values to logs, widgets, saved sessions, test snapshots or exception strings. Local development endpoint rules must be explicit and bounded to loopback. |

## Compatibility and migration

Keep the TUI's base Python 3.11 chat install working. Put a generated GraphOS operation client behind a compatible optional extra or runtime capability check. Document the precise supported Python range in package metadata and lock. Where legacy capability/run APIs remain, inventory their callers and retire each only after a public replacement is served. The GeniusBot consumer must independently prove the same versioned envelope and identity rules. This repository only supplies its contract expectations.

## Quality and reuse

Use the existing command registry, `AgentClient`, `httpx`, Textual widgets, and GraphOS generated models. Keep one transport normalization path and no duplicated request envelope construction. Run the repository's configured Ruff, type and pytest checks. The current repository has no configured CCCC, `jscpd` or Dupehound command or threshold. Before acceptance, either add shared ecosystem invocations with an explicit baseline or record an agreed exception. Do not claim a numerical pass without a configured tool. Apply KISS through a single client and one-use confirmation state. No unrelated `/docs` edit is required. Update README/configuration only where command or credential setup changes, and update AGENTS/constitution only if the contract itself changes.

## Structure parity with agent-webui (2026-10-11)

The operator requires agent-terminal-ui to use the same structure as agent-webui. The table compares structure only.

| Element | agent-webui | agent-terminal-ui | Action |
|---|---|---|---|
| Specs | 6 area specs | 1 spec (`terminal-runtime`) | Decisions below; no new directory |
| Workflows | `advisory.yml`, `release.yml` | `pages.yml`, `pipeline.yml` | Differs in names; add release caller (R007) |
| Pages caller | `pages_pipeline.yml@main`, `spec_dashboard_enabled: true` | same | Same |
| Python pipeline caller | none seen | `python_pipeline.yml@main` | Keep |
| Pre-commit | `.config`/root config, 50+ hook ids incl. spec-standard, ste-staged, public-surface | root config, 26 ids | Add spec hooks (R004) |
| `pyproject` hook sections | `public_surface`, `ste` | none | Add (R006) |
| Packaged development skill | present | missing | Add (R003) |
| Docs | start, status, deployment, design-system, apps, atlas, others | agent_view, configuration, session pages | Add four pages (R005) |
| `mkdocs.yml` | present | present | Same |
| AGENTS.md | Commands, Quality gates, Branching, Documentation, Specs | Working discipline, worktrees, Specs | Add headings (R009) |

Area decisions, from the terminal code:

| webui area | Terminal client has it? | Decision |
|---|---|---|
| Design system | Yes: `app.py` selects a Textual theme (`tokyo-night`) | New rollup `TUI-RUNTIME-R008` in the existing spec |
| Decision evidence | Partly: `app.py` approval decisions, covered by `R001.5` | No new row |
| Finance asset manager | No: `git grep` for finance and asset finds nothing | No spec |
| API consumer | Yes: `client.py` GraphOS boundary, owned by `R001` and `R002` | No new row |
| App surfaces | Yes: `screens/`, owned by `R001.7` | No new row |
| Identity and access | Yes: bearer caller identity, owned by `R001.2` | No new row |

## Run harness surface (TUI-RUNTIME-R010)

### Existing source and planned wiring

`CommandProcessor.cmd_run` (`agent_terminal_ui/commands.py:244`) → `open_run_inspector` (`app.py:869`) → `RunInspectorScreen._poll_once` (`tui/run_inspector.py:399`) → `AgentClient.get_run_summary` (`client.py:804`).

Current source ends at `GET /api/runs/{id}`. It does not invoke `runs.get` or `runs.metrics`.
The implementation must migrate this existing path only when the registered replacement has served proof.

The client must use the versioned GraphOS operation transport and its generated envelope.
It must not add another HTTP stack or call the engine directly.

### Model and wire-to-view mapping

[GraphOS run reads](https://github.com/Knuckles-Team/graph-os/tree/main/specs/hosted-api-operations) own the served projection.
`GRAPHOS-OPS-R021.4.5` serves per-run fields; `.3` and `.4` define aggregate models and operations.
`GRAPHOS-OPS-R021.4.6` supplies registration and generated artifacts.

| GraphOS wire field | View label and behavior |
|---|---|
| `termination_reason` | Distinct final answer, context overflow, stuck, step budget and error labels |
| `peak_context_tokens`, `context_budget_tokens` | Peak context tokens against run budget; never current occupancy |
| `cost_usd` | Per-run USD cost |
| `harness_config_ref`, `harness_config` | Applied decision reference and available configuration fields |
| `current_plan` | Available snapshot items, revision and observation time; read-only |
| `runs.metrics` result `cost_per_solved_task_usd` | Aggregate cost per solved task, with query grouping and abstention |

The client must not accept RDF camelCase fields as alternate wire names.
The client must preserve null availability and measured zero as different values.
The engine defines solved tasks and computes aggregates under `EG-ORCH-VOCAB-R010`.
Zero-solved cost abstention must display unavailable, never zero or per-run cost.
Pair-level rates and configuration-level costs must retain separate group labels.

### Current-plan prerequisite and refusals

`AU-HARNESS-R014.1` through `.5` own mutable `PlanState` outside stored message history.
Those rows supply no public snapshot read contract today.
`GRAPHOS-OPS-R021.4.5` defines the required cross-boundary snapshot and blocks availability until the AU producer exists.
The client must not derive a plan from messages, reconstruct state, or add a plan writer.
An available empty plan must differ from unavailable state.
Run switches, denied refreshes and expired snapshots must clear protected values from the previous display.
A missing plan must not suppress other independently available trace fields.
Unknown terminal reasons must display unavailable; the client must never infer success from a final answer alone.

### Evidence and implementation order

Implement the GraphOS producer before the consumer wiring, then field rendering and served acceptance.
The six existing children remain the only client requirement family for this surface.
The tests in test-spec.md are planned acceptance paths, not proof of implementation.
Each row requires its own positive and negative served case through the production UI path above.

### Amendments

- 2026-10-11, rows `TUI-RUNTIME-R003` to `TUI-RUNTIME-R009`: the operator required agent-terminal-ui to match agent-webui structure. The old state had no structure rows. The new state adds seven rollups. Evidence: the comparison table above.

<!-- spec-definition-patch:r002-consumer-plan -->
## TUI-RUNTIME-R002 consumer boundary

The GraphOS owner must publish contracts R009.2 through R009.6 and R010.7. Those contracts bind a versioned HostLaunchReceipt, interface mode, workspace and opaque tenant-authorized log reference. GraphOS authorizes each read and reconnect. It supplies record order and rotation gaps. These IDs are producer prerequisites. They do not claim existing runtime exports. The terminal never grants authority or reads a local log path. R010.7 places web_logs in HostLaunchRequest, but the current HostLaunchReceipt v1 contract omits it. GraphOS must bind the effective boolean into an authenticated receipt or handoff, scoped to host, workspace, tenant and principal. Until GraphOS supplies that field, TUI log reads stay disabled. The required host redacted sink remains enabled. This is a producer prerequisite, not a claim of an existing export.

Dependency order:
1. Keep the original R002 chat transport acceptance in child .1.
2. Consume the receipt. Validate version, readiness, endpoint, session, workspace, host, mode, tenant, expiry and bound web_logs preference.
3. Define the adapter signature: `agent_terminal_ui.app.run_host_terminal(receipt: HostLaunchReceipt, *, client: AgentClient, log_reader: HostLogReader | None) -> None`.
4. Define HostLogReader in agent_terminal_ui.client. Its asynchronous method is `read(log_ref: str, *, cursor: str | None, limit: int) -> HostLogBatch`.
5. Subscribe in terminal and both modes only when the bound web_logs preference is true. A false or absent preference and every web-mode case make zero TUI reads; chat continues. Keep the required host sink enabled. Reuse CommandProcessor.cmd_logs, MainScreen.action_toggle_logs and RichLog.
6. Bound reads, queued bytes, lines, timeouts and cancellation as requirements.md states. On rotation, expose a tenant-local gap. On denial, clear protected state. Never stop GraphOS resources.
7. Exercise the full served path on a real host, client and TUI. Use the fixed seed and two tenants after producer contracts are available.

The TUI defines consumer interfaces here. It does not claim existing exports. Extend AgentClient, the application, CommandProcessor.cmd_logs and MainScreen.action_toggle_logs. Do not add another router, transport, local gateway or file reader. This slice leaves the TUI-RUNTIME-R010 inspector obligations intact.

AU:116 SHA-256 08a22602bd677e4fc39260d058503fa73a2216ad40bbe817c17d3bef256722ef. Map the remaining TUI obligation to R002.2, .3, .5 and .6.
AU:117 SHA-256 fddbc1b35588be4427396a7aa827414d9d7bba01a8837f905a8b1c9b1eac4694. Map its remaining mode and unified-view obligation to R002.2 through .6, especially .4. R002.1 preserves the parent acceptance. These are definition mappings only.
<!-- /spec-definition-patch -->

## Amendments

### 2026-10-13: Rust thin-client migration (R002, R001, R008, R010)

Decision: use Rust with Ratatui for native terminal rendering and Tokio for asynchronous execution. Keep GraphOS as
runtime, policy, authentication, task and operation authority. EG owns graph
storage and reasoning. The terminal must not embed a graph replica, planner,
model runtime, tool executor or second MCP authority. Existing Python stays
available until a release candidate passes the same served journeys.

Source baseline: TUI `5ac5e3fec4d590f167d2c6bd694683dbd8950c26` uses A2A
chat plus REST, not ACP. The reviewed GraphOS `660412bf` dispatcher lacks served
`message/stream` and refuses `tasks/resubscribe` and `graphos.plan/confirm`.
These are producer prerequisites, not working features. Client mocks and
Agent Card claims cannot close them. Record producer head and served receipts
before enabling each feature. No downgrade to an untyped or local effect path.

```text
terminal input -> command intent -> bounded asynchronous transport queue
    -> authenticated GraphOS A2A / versioned operations
    -> bounded normalized events -> view-state reducer -> terminal frame
GraphOS -> runtime / policy -> EG graph and reasoning
```

Use one transport adapter per frontend process. Port the existing AgentClient
normalization and CommandProcessor semantics; share public wire fixtures with
Python instead of building a second protocol. The renderer draws presentation state
only. The asynchronous runtime owns transport, cancellation, deadlines and bounded queues. UI
input and resize must remain responsive while a request or reconnect is pending.
The operator selected Ratatui. Acceptance measures rendering behavior, not the library brand.
Preserve keyboard navigation, dynamic theme tokens, no-color and reduced-motion
behavior, selection and scroll position. Approval uses a distinct modal.

Keep server task ID, context ID and run ID as separate opaque values. A local
view ID is never a substitute. Store server correlation explicitly; do not infer
run identity from a task string. Reconnect retains these bindings. Duplicate
events are idempotent by stream generation and sequence. A gap or cursor expiry
invalidates the affected view and requires an authorized snapshot plus a new
cursor. Never replay a submission, confirmation or cancellation as a new task.
Unknown submission outcome requires reconciliation or explicit user action.

Cancellation requests the existing server task cancellation and waits for its
acknowledged state. A local canceled future is not proof of remote cancellation.
A disconnect displays unknown/pending state, retains identity and offers recovery.
Approval fails closed during disconnect, missing capability or missing signed
pending-call identity. PLAN confirmation retains exact reference, subject,
parameters digest, registry digest and expiry; only GraphOS authorizes effects.
Revocation clears protected views and pending plans before further rendering.

Start with direct remote service access. A local UDS or Windows named-pipe broker
is optional only after the benchmark below proves a net benefit. It may cache
only authorized views scoped by principal, tenant, workspace, endpoint and
policy epoch. Peer credentials and restrictive socket/pipe ACLs are required;
a local connection never grants GraphOS authority. No public listener or shared
cross-principal cache. Bound bytes and events per subscriber. Disconnect slow subscribers with an
explicit gap. Recover through retained replay or an authorized resnapshot. Revocation, logout and expiry invalidate cached data and cursors.
The broker must not interpret graph state or call MCP tools independently.

### Spec-delivery record

This amendment defines the migration under existing R002, preserves all R001
approval and R010 run-observation obligations, and extends R008 presentation
acceptance. Definitions are proposed for review; no Rust runtime is delivered
or verified. Existing generated VERIFIED labels describe source/test bindings,
not served deployment proof. The missing producer methods remain blockers.
Keep pipeline callers and shared hooks at `@main` / `rev: main`. Parent reviews
and merges the non-draft PR. No version or dependency change is needed here.

### OpenCode coexistence and cutover

The goal is a native terminal connected directly to GraphOS that replaces
OpenCode. First establish working OpenCode access to the terminal development
skill and GraphOS. Keep OpenCode installed and usable throughout implementation
and validation. A Rust build or mock test cannot authorize its removal.

Before cutover, demonstrate skill discovery and invocation in both clients.
Prove parallel GraphOS agents, streaming, cancellation, approval refusal and session recovery. GraphOS owns parallel task admission and
lifecycle; the TUI only presents and controls authorized tasks. Preserve each
agent's task/context/run bindings. Do not spawn a second local orchestrator.
Record exact client and producer heads, served receipts and parity gaps. Require
operator approval after parity evidence and the performance gates pass. Keep a
working OpenCode rollback path until the operator accepts the replacement.

Canonical skill: `agent_terminal_ui/skills/agent-terminal-ui-development/SKILL.md`.
OpenCode provisioning must expose that maintained file, rather than a forked
copy of its instructions. Provisioning itself is not delivered by this spec.

### Native discovery entry point (R002.7)

The separate native/agent-terminal-ui executable reads the existing AGENT_URL
and AGENT_BEARER_TOKEN settings. Its single HTTP client fetches
/.well-known/agent-card.json. Ratatui renders discovery state while Tokio handles
the request and terminal input. A response name does not prove task capabilities.
The c key cancels local discovery; r retries after completion; q exits and
restores the terminal. There is no task, approval or engine execution path.

The Python executable and OpenCode remain available. Native compilation uses a coordinated validation slot. Source and format checks
alone do not establish delivery or served GraphOS acceptance.

The initial Linux check passed six native tests with real loopback HTTP fixtures.
The cold two-job build took 38 seconds. Formatting and Clippy passed with warnings
denied. A pseudo-terminal smoke passed discovery, refusal/retry, cancellation and terminal restoration.
This evidence covers discovery only. No configured live GraphOS endpoint
was available, and no served streaming or approval acceptance is claimed.

### 2026-10-13: Native task correlation model (R002.1.1)

Reuse AgentClient's task, status-update and artifact-update wire fields. Add a
native typed model with an immutable task/context/run binding and explicit
validation before returning an event. Share a redacted JSON fixture with the
Python normalizer tests. This model has no network or retry behavior. Native
submission and streaming still require the missing served producer proof.

### 2026-10-13: Unary snapshot delivery and remaining producer gaps

Rechecked TUI main 4239e3b and GraphOS main 331044ed. The authenticated
GraphOS A2A facade serves tasks/get and tasks/cancel. The separate agent-host
endpoint supports message/send only. An Agent Card alone does not prove task
read capability. The native task view uses only the unary tasks/get method.

GraphOS still lacks message/stream. Its tasks/resubscribe handler returns an
explicit refusal. Host receipts, bound web_logs and log-reader exports remain
specifications. R002.1.3 and R002.2 through R002.6 stay pending. OpenCode and
Python remain available. No cutover, performance or complete migration claim
is made by the model and snapshot children.

Native HTTP tests cover the request, credential, response bounds and refusals.
The executable was also checked through the real GraphOS HTTP handlers and
A2AService with upstream test authority and authentication fixtures. That
check covers the handler boundary, not production identity, tenant isolation,
TLS or WorkItem authority. It requires no native EG build.

### 2026-10-14: Native unary submission increment (R002.1.3.1)

GraphOS main 0120e1f serves ordinary text tasks through message/send with
request-bound authentication, WorkItem admission and the existing AU dispatch
queue. Add one native --prompt submission, then retain the acknowledged task
binding in the existing refresh and cancellation view. Generate the request
identity once. Do not retry an effect or replay it on refresh. An interrupted
submission has an unknown outcome. Reject a prompt combined with AGENT_TASK_ID.

Verify the native executable against the actual GraphOS request handler,
WorkItem submission and AU enqueue functions. Control the final storage and
queue boundaries. Check the authenticated carrier and zero admission for
denied requests. This proves the submission adapter, not durable engine or
worker completion. Preserve production-profile refusal when its configured
dispatch authority is absent. Streaming, session recovery, the six original
requirements and OpenCode cutover remain pending.

R002.1.3 now rolls up this bounded adapter in R002.1.3.1 and the preserved
original served integration acceptance in R002.1.3.2. Retain every parent criterion. A fixture-only positive response cannot close
the parent.

### 2026-10-13: Original cancellation criterion

The nearest available R002.1 producer is tasks/cancel. GraphOS main 331044ed
already routes this method to WorkItemA2AAuthority. The native consumer
requires explicit confirmation and a matching canceled response. An interrupted
request has an unknown outcome until a read reconciles it. The client never retries an effect automatically.

Missing producer contracts remain with GraphOS. GRAPHOS-A2A-R001 and
GRAPHOS-A2A-R010 own durable streaming and resubscribe. Their spec names the
AU-CONTROL-001 event port; a current AU owner row was not found.
GRAPHOS-HOST-R009.2 through GRAPHOS-HOST-R009.6 and GRAPHOS-HOST-R010.7 own the host/log journey.
GRAPHOS-A2A-R005.2 and GRAPHOS-A2A-R006.2 retain approval and verified-caller prerequisites.
Coordinate those changes with the parent before touching active producer work.

The native suite passed 32 tests, including the configured ten-second timeout.
Formatting and strict Clippy checks passed. Six pseudo-terminal cases passed
through GraphOS handlers, A2AService, WorkItemA2AAuthority and the AU cancellation adapter.
They cover confirmation, dismissal, refusal, response loss after commit, local interruption and read reconciliation.
Each case checked wire counts and terminal restoration. The fixture uses a
synthetic session and scripted storage. Native EG storage, worker interruption,
production authentication and TLS remain unqualified. The original six migration
rows remain pending. Keep OpenCode until served parity and cutover acceptance pass.

## One-shot tool-task consumer

Component: Terminal task view
Depends-on: TUI-RUNTIME-R001.2, TUI-RUNTIME-R001.3, TUI-RUNTIME-R001.5, [GraphOS A2A](https://github.com/Knuckles-Team/graph-os/blob/331044ed7daec51a3633e0a7ea712293b2063bf3/specs/a2a/spec.md)

Code: ../../agent_terminal_ui/terminal_ui.py:10

Code: ../../agent_terminal_ui/client.py:520

Code: ../../agent_terminal_ui/client.py:587

Code: ../../agent_terminal_ui/client.py:597

Code: ../../agent_terminal_ui/headless.py:163

Existing code: terminal_ui dispatches CLI options; AgentClient owns task transport and the headless path owns streamed rendering.
Reachable today: no exact one-shot tool-task command or matching-scope preapproval projection is present.
The native model and read-only snapshot slices remain separate from the required served one-shot transport.

The CLI must add --one-shot as one explicit mode, exclusive with --prompt and --headless.
Read exactly one UTF-8 JSON object from standard input without echoing or logging its bytes.
Never accept request parameters or preapproval_ref through command arguments.
The input object must contain operation_id, object parameters and idempotency_key; preapproval_ref is optional.
Reject unknown fields, duplicate JSON keys, malformed objects and inputs above 64 KiB before any network call.
The client must validate the operation and schema through the existing generated registry under R001.
The client must create one request binding before submission and retain it across reconnect.
AgentClient must add a typed message/send method beside its existing text-only stream method.
The terminal must send the typed payload through that method, never reinterpret it as an unstructured prompt.

Producer dependency: GraphOS must publish the exact message/send tool-task payload schema and preapproval projection under GRAPHOS-A2A-R005 and GRAPHOS-A2A-R006.
The existing public A2A contract defines task methods and pending-call approval; it does not define that tool-task payload.
The initial scope receipt must bind caller, tenant, workspace, operation, parameter digest, policy revision, registry digest and expiry.
After admission, GraphOS must bind that receipt to the task and exact pending call before attesting prompt suppression.
The final pending-call binding must come from the server after task admission, never from caller-supplied identity fields.
The one-shot request authorizes one connector operation invocation, without expanding its granted scope.
GraphOS must consume the final pending-call grant atomically and dispatch that operation at most once.
Progress and task events do not authorize additional connector invocations.
A valid preapproval may suppress presentation of a prompt; it must not bypass server admission or console step-up.
The complete GRAPHOS-A2A-R005.2 signed chain and GRAPHOS-A2A-R006.2 caller bridge remain prerequisites.
Missing binding or served authority proof must keep prompt bypass disabled.
This consumer definition must not invent a producer export or claim the original cross-owner obligation is complete.

Observation must use tasks/get and tasks/resubscribe with the original opaque task identity.
Use the existing bounded transport queue and renderer, preserving output order and explicit gaps.
An explicit cancel must call tasks/cancel and wait for acknowledgement before displaying cancelled.
Detach must stop only the owned observer and print its opaque task identifier without credentials.
A later --observe-task TASK_ID invocation must authenticate and use tasks/get followed by tasks/resubscribe.
That mode must never submit an operation, accept preapproval or invoke confirmation.
It must refuse --one-shot, --prompt and --headless combinations.
A denied or unknown task must reveal no output.
Terminal loss must not imply remote cancellation or successful completion.
The terminal must clear protected output when authorization expires or the caller changes.

```mermaid
sequenceDiagram
  participant C as Terminal CLI
  participant T as Existing AgentClient
  participant G as GraphOS A2A authority
  participant B as Governed tool backend
  C->>T: Validated one-shot request
  T->>G: message/send with fixed idempotency key
  G->>G: Bind task and validate authority
  G->>B: Admitted tool effect
  G-->>T: Task identity and ordered events
  T-->>C: Lifecycle, output and termination
  C->>T: Cancel selected task
  T->>G: tasks/cancel
  G-->>C: Cancellation acknowledgement through client
```

Decision: reuse the existing task transport and renderer; reject local task execution and unconditional approval flags.
Implement the producer binding first, then the typed input, observation, refusal, evidence and served proof children.
The planned tests must cover both frontend implementations before native cutover, using identical task and scope fixtures.

## TUI-RUNTIME-R001.8

`TUI-RUNTIME-R001.8`: Extend command/client contract for one-shot background tool-task submission with GraphOS preapproval binding gate.

## Coding session (TUI-RUNTIME-R011)

Extended or new: new rollup; no existing rollup owns the coding session (search terms: coding, workspace root, diff, resume).

Data flow, in order:
- `terminal_ui` (`agent_terminal_ui/terminal_ui.py:10`) opens the session with the workspace root.
- `AgentClient._rpc_stream` (`agent_terminal_ui/client.py:353`) delivers an agent request.
- The new `CodingSessionView` handler (`agent_terminal_ui/coding_session.py`) receives it.
- `WorkspacePolicy.check_operation` (`agent_terminal_ui/workspace_policy.py:177`) checks containment.
- The view displays the diff or command, and the person approves.
- The host performs the local read, write or process, and the result returns to the gateway.

Existing code:
- `agent_terminal_ui/client.py:338` and `:353`: JSON-RPC over HTTP for agent tasks only; no `fs/` or `terminal/` method.
- `agent_terminal_ui/app.py:7`: docstring only.
- `agent_terminal_ui/app.py:572` and `agent_terminal_ui/tui/tool_approval_screen.py:35`: tool approval modal.
- `agent_terminal_ui/screens/permissions.py:164`: PermissionsScreen, exported at `agent_terminal_ui/screens/__init__.py:13`, never pushed.
- `agent_terminal_ui/danger.py:229`: command danger level.
- `agent_terminal_ui/workspace_policy.py:63`, `:177`, `:214`, trust mode `:104`, and `agent_terminal_ui/settings.py:197`.
- `agent_terminal_ui/workspace_snapshots.py:50`, `:158`, `:229`, `:357`, and `agent_terminal_ui/settings.py:176`.
- `agent_terminal_ui/session_manager.py:161` and `:303`.
- `agent_terminal_ui/app.py:695`: resume of a stored chat, reached from `agent_terminal_ui/commands.py:260`.
- `agent_terminal_ui/headless.py:163` and `opencode.json:1`.

Reachable today: no for the coding session. Only `ToolApprovalScreen` (`app.py:608`) and chat resume (`commands.py:260`) are reached by a production caller, and neither serves a file or terminal request. `WorkspacePolicy`, `WorkspaceSnapshotManager`, `SessionManager` and `PermissionsScreen` have no production caller; the grep `git grep -n -E "WorkspacePolicy\(|WorkspaceSnapshotManager\(|SessionManager\(|PermissionsScreen\("` finds none outside their own modules. The search for `fs/`, `terminal/` and `request_permission` finds no handler.

Types and fields: `CodingSessionView(root, capabilities, session_id, pending)`; capability set closed to six methods; refusal enum of five reasons.

Attach point and caller: the handler attaches to the stream loop at `agent_terminal_ui/app.py:484`; its production caller is the running `terminal_ui` application.

Failure behavior: a gateway loss keeps the pending request, answers nothing, and resumes without granting.

Decision: the client performs file and terminal actions on the host as protocol client capabilities. `GRAPHOS-ACP` owns admission and permission rules. `AU-CONTROL` exposes the tools. Rejected: a cluster service that mounts or syncs the host checkout. It copies data and needs host credentials on the cluster.

Cross-repository rows: `GRAPHOS-ACP` contract `CodingSessionAdmission`; `AU-CONTROL` contract `ClientCapabilityToolset`; `EG-DECISION-ENGINE` `HarnessConfig` supplies the tool selection. This repository states only `CodingSessionView`.

References: none; no paper is cited.

### 2026-10-16: Native approval state boundary (R011.1, .4, .5, .7, .11)

`native/agent-terminal-ui/src/coding_approval.rs` is the Rust presentation
attachment for this slice of `CodingSessionView`. It holds exact pending request
content, previews the full diff or command, and records an explicit choice bound
to that preview. Changed, foreign and completed request IDs cannot reuse a choice.
Gateway loss retains unanswered requests. Reattachment does not approve them.
Records contain request/session identity, method, resolved path or adapter-supplied
command digest, choice and actor. Preview bodies never enter records.

The module has no file, process, persistence or transport effects. Its choice is
not a GraphOS permission grant. The future admitted-session adapter must verify
scope, capabilities, resolved paths, content/digest bindings and permissions before
calling it, and recheck before any effect. Diff inputs are authorized old/new text;
command digest comes from that adapter. No digest algorithm or wire field is added.

`native/agent-terminal-ui/tests/coding_approval.rs` covers the state boundary and
Ratatui preview. The native application and client must attach it after
`CodingSessionAdmission` and `ClientCapabilityToolset` are implemented. Existing
Python attachment references remain historical and are replaced by Rust only for
this view slice. Durable resume, host effects, containment and served entry-point
proof remain open. The existing twelve rows are not promoted by these unit tests.

The library exports `coding_approval` through its public API. Focused tests import
that API, so normal crate compilation includes the module. Production view/key
attachment and authorized producer adapters remain deferred.
