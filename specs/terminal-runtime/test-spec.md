# TUI-RUNTIME test specification

| Requirement | Layer and fixture | Expected positive result | Required negative proof |
|---|---|---|---|
| TUI-RUNTIME-R001.1 | Unit command parser plus `httpx.MockTransport`; installed generated registry artifact | Known op and object params produce one versioned request with correct envelope | Empty ID, malformed JSON, array input, unknown op, missing registry file and digest mismatch make zero effect requests |
| TUI-RUNTIME-R001.2 | Client transport with loopback and remote URLs, fake bearer | Verified caller header reaches remote Arbora only over TLS | Remote HTTP, absent/invalid bearer, credential in exception/log/snapshot all fail |
| TUI-RUNTIME-R001.3 | A2A fake server that issues a PLAN with binding and expiry | One `/confirm` resumes exactly the issued plan | Tampered op/input/digest/subject, expired plan and replay are rejected before any effect; server also rejects stale lease |
| TUI-RUNTIME-R001.4 | Mock error envelope, timeout, disconnect and malformed JSON | Typed success renders and chat remains functional | Every failure renders an error, leaves session usable and never reports success |
| TUI-RUNTIME-R001.5 | Pending A2A task with `input-required` and approval metadata | Pending request is displayed. No effect is asserted | `approvals.*`, fleet grant, missing signed exchange and wrong pending-call binding are refused. Enabling approval requires separate served receipt |
| TUI-RUNTIME-R001.6 | Clean Python 3.12 base environment and supported optional-client environment | Base chat works. Compatible optional install enables `/op` | No compatible client yields clear `CLIENT_UNAVAILABLE` and no untyped fallback |
| TUI-RUNTIME-R001.7 | Route and pilot tests | Legacy screens still render or use served replacement | No `agent_utilities.knowledge_graph` import, duplicate transport or invisible command fallback |

## Integration and acceptance receipts

1. Build and install wheels from pinned public revisions of this TUI and Arbora. Verify the generated operation registry is packaged, not only importable from a source checkout.
2. Use a reproducible local Arbora service fixture to prove discovery, authenticated invocation, PLAN confirmation, error envelope and read-only chat continuity. A contributor must be able to run this without an organization network.
3. Run command, client and component tests, type/lint checks and package metadata checks. Run the CI matrix on supported Python versions. Capture exact public commit/check links in `status.json`.
4. Separately prove the served human-to-WorkItem approval binding before enabling approval routes. A pending task display is not an approval receipt.
5. Run configured CCCC, `jscpd` and Dupehound ecosystem checks if installed. They are currently absent from this repository's tracked configuration. Record that as an acceptance gap until thresholds and commands are published. Review KISS against the reuse table in `plan.md`.

No manual-only proof substitutes for the negative tests. If a live identity provider is unavailable, keep approval disabled and acceptance pending. Baseline tests must not require private infrastructure.

## Structure parity rows

| Requirement | Layer and fixture | Expected positive result | Required negative proof |
|---|---|---|---|
| TUI-RUNTIME-R003 | File-level unit test in `tests/test_skill_package.py` | Wheel contains the skill | Skill missing from wheel fails |
| TUI-RUNTIME-R004 | Child proofs in `tests/test_precommit_hooks.py` | Shared spec enforcement and weekly repository checks follow policy | Missing coverage or a nonblocking spec command fails |
| TUI-RUNTIME-R005 | File-level unit test in `tests/test_docs_layout.py` | Four pages exist and are in nav | A page absent from nav fails |
| TUI-RUNTIME-R006 | File-level unit test in `tests/test_precommit_hooks.py` | Both sections present | A missing section fails |
| TUI-RUNTIME-R007 | File-level unit test in `tests/test_docs_layout.py` | Workflow calls pipelines at main | A SHA pin fails |
| TUI-RUNTIME-R008 | File-level unit test in `tests/test_app_handlers.py` | Default theme and no-colour fallback hold | An unknown theme name falls back, not crashes |
| TUI-RUNTIME-R008.1 | Production native draw function with Ratatui TestBackend | Resize from 100 to 40 columns preserves wrapped discovery status and complete keyboard help; Tokyo Night tokens render | Nonempty NO_COLOR resets foreground and background; unsupported AGENT_THEME falls back without panic |
| TUI-RUNTIME-R009 | File-level unit test in `tests/test_docs_layout.py` | Four headings present | A missing heading fails |

## Planned run-surface acceptance

These tests are planned, not execution receipts. Each test must bind its exact requirement ID.
Each case must enter the production UI, existing client, and a served Arbora operation fixture.
A mocked widget value alone must not count as served evidence.

| Requirement | Planned test | Positive served requirement | Negative served requirement |
|---|---|---|---|
| TUI-RUNTIME-R010.1 | `tests/test_run_inspector_contract.py::test_run_read_uses_arbora_operations` | A selected run must render through the served operation and existing client. | Absent registration, timeout or denial must display unavailable without direct engine calls. |
| TUI-RUNTIME-R010.2 | `tests/test_run_inspector_contract.py::test_harness_config_shown` | A committed configuration must retain its reference and values through the client. | Missing or inaccessible configuration must not use defaults or the latest configuration. |
| TUI-RUNTIME-R010.3 | `tests/test_run_inspector_contract.py::test_context_and_cost_shown` | Measured zero must render as zero; aggregate cost must retain its solved-task label. | Null values must display unavailable; zero-solved abstention must not render zero cost. |
| TUI-RUNTIME-R010.4 | `tests/test_run_inspector_contract.py::test_plan_read_only` | A fresh matching snapshot must preserve item order, revision and AU statuses. | Expired, wrong-run, regressing or unavailable snapshots must reveal no items or edit controls. |
| TUI-RUNTIME-R010.5 | `tests/test_run_inspector_contract.py::test_termination_reasons_distinct` | Each of final_answer, context_overflow, stuck, step_budget and error must have its own label. | Unknown or missing reasons must display unavailable; overflow and stuck must not collapse to generic failure. |
| TUI-RUNTIME-R010.6 | `tests/test_run_inspector_contract.py::test_run_surface_end_to_end` | A served fixture must render summary, configuration, context, cost and an available plan. | Denied reads after success must clear prior protected values; the UI must stay responsive without fabricated data. |

<!-- spec-definition-patch:r002-consumer-tests -->
## TUI-RUNTIME-R002 acceptance matrix

The served acceptance uses the normal mode selector, public adapter, authenticated Arbora reader and production TUI. Mocks may support unit tests. They cannot replace this path.

| ID | Positive case | Negative and boundary case | Evidence |
|---|---|---|---|
| TUI-RUNTIME-R002.1 | The canonical transport authenticates a session. It streams a reply and cancels an active turn. | Keep the prior route until all original cases pass. A transport failure never reports success. | Served session, authentication, streaming and cancellation results. |
| TUI-RUNTIME-R002.2 | A ready v1 receipt binds host, mode, endpoint, session, workspace and an authenticated web_logs preference. | Missing or unbound preference, altered version, readiness, expiry, tenant, host, endpoint, session, workspace or generation yields zero reader calls. | Receipt and handoff fields, producer response and read counts. |
| TUI-RUNTIME-R002.3 | The public adapter sends the opaque reference to the injected reader. | Missing reader or reference returns unavailable and makes zero reads. The TUI never reads a filesystem path. | Observation through the adapter and served call path. |
| TUI-RUNTIME-R002.4 | With web_logs=true, terminal and both modes render one record through /logs and Ctrl+V during chat. | With web_logs=false or absent, terminal/both make zero TUI reads and chat continues. Web mode makes zero TUI reads for either value. The host redacted sink remains enabled. Literal content cannot inject markup or controls. Local input cannot change producer authority. | Served mode/preference matrix, TUI read counts, chat observations and host sink record. |
| TUI-RUNTIME-R002.5 | Two tenants share one workspace; each receives its own ordered records. Rotation emits a gap. Reconnect reauthorizes. | Foreign or revoked refs return no records or offsets. The UI clears old state. Slow rendering cannot block HTTP. | Per-tenant sequences, gaps, queue high-water marks, denial clearing and cancellation time. |
| TUI-RUNTIME-R002.6 | A live host request appears beside chat in terminal/both when web_logs=true. Disabled preference keeps chat and the host sink available. | Missing/unbound preference, web mode, or disabled terminal/both yields zero TUI reads. Revocation clears state before reconnect. Slow rendering leaves live HTTP responsive. | Seed 116117 creates two tenants with separate principals in one workspace. Each emits 128 request IDs. Run twice. Normalize timestamps. Compare ordered IDs, sequences and gaps per tenant. Exercise every mode with web_logs on/off, rotation, reconnect, revocation and denial. Measure request-to-render time below two seconds. Track HTTP response, reader counts, host sink availability and producer/consumer revisions. Save no credentials or raw logs. |

Limits: one read in flight and 128 records per batch. Cap each record at 16 KiB. Cap pending data at 128 records or 2 MiB. Keep the view to 1000 lines. Use a one-second read timeout and five-second cancellation timeout. Replay compares IDs, order and gaps. Ignore wall-clock values.
<!-- /spec-definition-patch -->

## Rust migration acceptance (R002, R008; preserves R001 and R010)

Run Python baseline and release-mode Rust candidate on the same host, terminal,
120x40 viewport, credentials scope and deterministic redacted fixture. Record
both exact heads, OS, CPU, memory, terminal, compiler, build flags and dependency
lock. Network readiness is measured separately from first usable local frame.
No benchmark has run for this definition.

| Metric | Procedure | Candidate acceptance target |
|---|---|---|
| Cold process | Start 30 fresh processes per candidate. Report p50/p95 exec-to-first usable frame. Record page-cache conditions separately. | p95 <= 200 ms and no worse than Python |
| RSS | Record process-tree peak and steady RSS after 60 seconds for identical 1000-line view | steady <= 40 MiB, peak <= 64 MiB and <= Python |
| Idle CPU | After 30-second settling, measure CPU-time/wall-time over 60 seconds without events | <= 0.5% of one core per client |
| p95 render | 10,000 events at 100/s; timestamp adapter receipt through frame flush; include resize and key input | p95 <= 50 ms, p99 <= 100 ms; no hidden drops |
| Multiple clients | Repeat with 1, 4 and 16 clients. Use shared and distinct principals. Include a slow reader and a disconnect. | Latency targets hold. No protected data crosses scope. Memory and queue limits hold. |

These are acceptance targets, not measured claims. If hardware cannot meet a
target, revise it with baseline evidence before acceptance. Report raw samples,
percentile method and failures; do not average away a slow client. Broker trials
must include broker RSS/CPU in totals and demonstrate at least 20% lower total RSS or
upstream request count at 16 clients, with no latency regression. Otherwise keep
direct access. Limit each transport subscriber to 128 events and 2 MiB; exceeding
either produces explicit backpressure/gap handling rather than silent loss.

Protocol cases cover unavailable message/stream and refused resubscribe and
plan/confirm. Test duplicate/out-of-order events, cursor expiry and interrupted
submit. Test authentication expiry, revocation after success, cancellation
before/after acknowledgement and reconnect during approval. Assert exact task/context/run bindings and zero
automatic effect retries. A stale or denied snapshot clears protected values.
Test Python and Rust against the same wire fixtures, then repeat through the
served Arbora entry point. A fake server pass is not served acceptance.

Broker qualification also checks socket/pipe permissions, impersonated
principal, mixed tenants, changed policy epoch, bounded retention and a slow
subscriber. Every rejected scope yields zero protected records. Record replay
sequences and resnapshot generation; no independent graph or MCP path is allowed.

## OpenCode cutover evidence

Start from working OpenCode skill access and Arbora connectivity. Keep that
installation available while testing the native terminal. In each client,
discover and invoke the maintained development skill. Run two Arbora-managed
agents concurrently and stream both tasks. Cancel one without affecting the other.
Disconnect and recover the surviving task with unchanged task/context/run IDs.
Exercise approval denial, expired confirmation and identity mismatch. No client
may grant an effect locally. Compare served results and refusal behavior at
recorded client and Arbora heads. Cutover requires operator acceptance after
parity and performance evidence. Verify OpenCode remains a working rollback path.

## Native discovery tests (R002.7)

Run cargo test with the native/agent-terminal-ui manifest after slot allocation.
The discovery integration tests serve real loopback HTTP responses. They verify
the existing Agent Card route, caller header, invalid endpoint refusal,
authentication errors, redirects, malformed cards and cancellation during a
pending response. Renderer tests use the terminal buffer to verify refusal and
unavailable task actions. The size-limit case checks bounded input. A Linux pseudo-terminal smoke passed discovery, refusal/retry, cancellation and
terminal restoration. These fixtures are not a served Arbora deployment receipt.

## Native presentation acceptance remainder

TUI-RUNTIME-R008.2 remains pending. Test every supported theme, contrast, keyboard action, selection, scroll position and reduced-motion setting. Compare Python and native clients on the same fixture. Use the R002 render benchmark before acceptance. Discovery wrapping alone does not close this row.

## Native task correlation tests (R002.1.1)

Native tests consume the same task, status and text artifact fixture as the
Python normalizer. Assert three distinct IDs and preservation across valid events. Test missing task/context IDs, absent run without inference and each mismatched ID. Reject invalid status, artifact shapes and unknown kinds. Rejection must preserve the existing binding. Run the native
correlation integration test and the Python shared-fixture test. These tests do
not establish served Arbora streaming or cutover acceptance.

## Native task view

TUI-RUNTIME-R002.1.4 tests select an existing task with AGENT_TASK_ID. Display separate task, context and run IDs, with missing run labeled unavailable. A denied refresh clears prior values. Empty selection makes zero requests. Run the binary under a pseudo-terminal against the production Arbora HTTP handlers and upstream test authority. Verify local cancellation and terminal restoration. This fixture does not qualify production identity or tenant isolation.

## Native snapshot transport

TUI-RUNTIME-R002.1.2 runs loopback HTTP tests for tasks/get. Check the exact JSON-RPC request, credential and matching response. Reject HTTP errors, redirects, malformed or mismatched envelopes, invalid task shapes and oversized responses. TUI-RUNTIME-R002.1.3 remains pending until the original served chat and recovery matrix passes.

## Native unary submission

TUI-RUNTIME-R002.1.3.1 runs one native --prompt through message/send. Check
credential, fixed random request identity, returned task/context/run binding,
refresh and cancellation. Invalid arguments cause zero requests. Denied
credentials cause zero WorkItem admission. Lost acknowledgement or local abort
must display an unknown outcome; refresh cannot submit again. A controlled
storage port and the existing queue exercise the actual Arbora admission and
AU enqueue functions, including carrier verification. This does not prove
native engine durability or worker completion. TUI-RUNTIME-R002.1.3.2 retains
all original served chat, streaming, continuity and recovery acceptance.

## Original cancellation acceptance slice

TUI-RUNTIME-R002.1.5 uses the existing tasks/cancel producer. Check one confirmed
request, matching task/context/run identity and the server canceled state. Deny
a request and interrupt another after admission. Neither may report success.
Local interruption must label the remote outcome unknown. A later r action may
read state; it must not replay cancellation. Test confirmation dismissal and
discovery mode with zero effect requests. Enter the real Arbora HTTP handlers
and cancellation authority with a scripted work port. Record that boundary and
its exclusions. This slice does not close session, streaming or cutover checks.

## One-shot tool-task acceptance

| Requirement | Planned test | Required observation |
|---|---|---|
| TUI-RUNTIME-R002.8.1 | `tests/test_one_shot_task_contract.py::test_one_shot_request_and_scope_model` | Model acceptance in requirements.md must pass through the existing task path. |
| TUI-RUNTIME-R002.8.2 | `tests/test_one_shot_task_contract.py::test_one_shot_lifecycle_and_output` | Behavior acceptance in requirements.md must pass through the existing task path. |
| TUI-RUNTIME-R002.8.3 | `tests/test_one_shot_task_contract.py::test_one_shot_uses_existing_task_transport` | Wiring acceptance in requirements.md must pass through the existing task path. |
| TUI-RUNTIME-R002.8.4 | `tests/test_one_shot_task_contract.py::test_one_shot_preapproval_refusal` | Refusal acceptance in requirements.md must pass through the existing task path. |
| TUI-RUNTIME-R002.8.5 | `tests/test_one_shot_task_contract.py::test_one_shot_evidence_and_reconnect` | Evidence acceptance in requirements.md must pass through the existing task path. |
| TUI-RUNTIME-R002.8.6 | `tests/test_one_shot_task_contract.py::test_served_one_shot_scope_and_lifecycle` | Hot-path proof acceptance in requirements.md must pass through the existing task path. |

Seed 104 must create two principals, one workspace and a controlled connector with independently recorded effects.
Start the real CLI with one typed operation and its fixed idempotency key.
Observe one task, ordered output, separate task/context/run identifiers and a server terminal reason.
Test matching preapproval, absent approval, expiry, revocation, changed parameters, foreign principal and changed policy/registry revisions.
Only matching, admitted authority may allow an effect without a prompt; every other case must display pending or refusal.
The backend must observe zero unapproved effects and at most one connector operation invocation for the same admitted request.
Test duplicate events, out-of-order events, replay gaps, timeout after submission and cancellation before and after acknowledgement.
Reconnect must observe the same task and must not submit again.
Detach must print the task ID and preserve the remote task.
A new --observe-task process must authenticate again, observe the same task and make zero submission or confirmation calls.
Denied observation must reveal no output; denial after success must clear protected output.
Unknown JSON fields, duplicate keys and input above 64 KiB must cause zero network calls.
--override must never convert pending approval into authorization in this mode.
The fixture must record exact producer and consumer revisions and independent backend counts.
Unavailable producer contracts block acceptance; a mock client cannot replace served proof.

The fixture must send request JSON through standard input.
Assert that argv, stdout diagnostics, logs and exception messages contain neither raw parameters nor the preapproval reference.

## Coding session

The suite is `tests/test_coding_session.py`. It uses a fake gateway and a temporary workspace directory.

- TUI-RUNTIME-R011.1: Planned `tests/test_coding_session.py::test_session_model_closed_capability_set`. Unknown methods must map to a typed refusal.
- TUI-RUNTIME-R011.2: Planned `tests/test_coding_session.py::test_capability_handlers_serve_local_host`. A read inside the root must return file text and prompt zero times.
- TUI-RUNTIME-R011.3: Planned `tests/test_coding_session.py::test_path_containment_refuses_escape`. Parent segments, absolute paths and symlinks leaving the root must be refused with zero bytes read or written.
- TUI-RUNTIME-R011.4: Planned `tests/test_coding_session.py::test_write_shows_diff_then_applies_on_approval`. A denied write must leave the file bytes unchanged.
- TUI-RUNTIME-R011.5: Planned `tests/test_coding_session.py::test_command_displayed_before_run`. A denied command must spawn zero processes.
- TUI-RUNTIME-R011.6: Planned `tests/test_coding_session.py::test_terminal_output_streams_in_order`. Output above the limit must carry the truncation marker and kill must end the process.
- TUI-RUNTIME-R011.7: Planned `tests/test_coding_session.py::test_resume_reattaches_without_granting`. A resumed session must display the same pending write and apply no change before approval.
- TUI-RUNTIME-R011.8: Planned `tests/test_coding_session.py::test_requests_reach_view_from_client_stream`. A request in the stream must reach `CodingSessionView` once.
- TUI-RUNTIME-R011.9: Planned `tests/test_coding_session.py::test_entry_point_opens_session_at_cwd`. Starting in a temporary directory must send that root at `session/new`.
- TUI-RUNTIME-R011.10: Planned `tests/test_coding_session.py::test_typed_refusals_reach_gateway`. Each reason must produce one error response and zero host effects.
- TUI-RUNTIME-R011.11: Planned `tests/test_coding_session.py::test_evidence_record_has_no_secrets`. The record must carry the decision and omit file content.
- TUI-RUNTIME-R011.12: Planned `tests/test_coding_session.py::test_headless_coding_session_write_and_containment`. The test must observe the diff, the approved write and the refusal.

The fake gateway sends requests only; the test asserts file bytes and process counts on the host.

## TUI-RUNTIME-R010.7: Native inspector boundary

`native/agent-terminal-ui/tests/run_inspector.rs` imports the public library.
Six tests cover rendering, zero, configuration, distinct reasons, plan admission
and protected-value clearing. These fixtures do not prove served operations.
## TUI-RUNTIME-R011.13: Native approval boundary

`native/agent-terminal-ui/tests/coding_approval.rs` imports the public library.
Seven tests cover the closed capability set, previews, exact choices, metadata
and unanswered reconnect state. These fixtures do not prove admission or host effects.
## Scoped acceptance proof

- `TUI-RUNTIME-R008.2.1`: Native buffer tests check palette tokens, contrast, reset colors and stable frames.
- `TUI-RUNTIME-R008.2.2`: Native buffer tests check paging, resize, Unicode, short results and small viewports.
- `TUI-RUNTIME-R008.2.3`: Served parity and performance receipts remain required. Buffer tests alone cannot close this row.
- `TUI-RUNTIME-R008.2.3.1`: Clear selection before mount without an error. Select actual text in the mounted application, then clear it. Check a real terminal startup, completed reply and clean exit.
- `TUI-RUNTIME-R008.2.3.2`: Retain all parent presentation criteria, same-fixture Python/native journeys and the release-mode R002 performance procedure. Startup checks alone cannot close this row.
- `TUI-RUNTIME-R002.1.3.2.1`: Native recovery tests check retry limits, binding, refusal and zero effect replay.
- `TUI-RUNTIME-R002.1.3.2.2`: Full served receipts remain required. Local HTTP fixtures alone cannot close this row.

R010.8: Native decoder tests preserve measured zero and empty available plans.
They reject wrong-run, malformed, regressing and expired snapshots. Transport tests require registry membership and matching digests.
These local tests do not prove a served AU producer or production UI attachment.

R010.9 loop tests cover validated run selection, local cancellation, close, read refusal and idle plan expiry.
These local tests do not close the served R010.6 acceptance requirement.

- `TUI-RUNTIME-R002.1.3.2.2.1`: Native task_stream tests prove bounded parsing and validation before cursor acknowledgement.
- `TUI-RUNTIME-R002.1.3.2.2.2`: Served streaming and recovery receipts remain required; local decoder tests are insufficient.

## Unbound host-log refusal

TUI-RUNTIME-R002.9 binds to tests/test_host_log_refusal.py. Mount the actual
application with AGENT_LOG_FILE set. Observe zero pathname opens. Exercise
/logs and Ctrl+V with focused input. Require the same refusal and cleared
old content. An absent source adds no client calls. These tests do not prove
an authenticated host-log reader or served tenant isolation.

- `TUI-RUNTIME-R002.10`: Test bounded HTTP receipts and mounted log rendering, denial clearing, cancellation and borrowed resources. Separate controlled transport tests from a real Arbora sink fixture.

- `TUI-RUNTIME-R002.11`: Use loopback HTTP for authenticated reference/read, denial, expiry and response limits. Test view cancellation, literal rendering and bounded retention.

R002.1.3.2.2.3 tests cover exact opt-in requests, legacy omission and both unavailable reasons.
They reject malformed, oversized, unsafe and foreign projections before display. Retained run bindings cannot change or appear later.
Renderer tests display literal commit identity and clear it after failed reads. These fixtures do not prove served recovery.

- `TUI-RUNTIME-R002.11`: Version-two loopback responses preserve original log
  metadata in literal Python and native displays. A retained-history gap clears
  content and stops reads. Unknown conflicts and malformed metadata refuse.

| TUI-RUNTIME-R010.4.1 | tests/test_current_plan_view.py | Read the selected run. Display its current plan. | Clear on refusal, refresh, cancellation, invalid data and expiry. |
| TUI-RUNTIME-R012.4.2 | tests/test_served_fleet_usage.py | Read opaque pages and tenant totals. | Refuse failed or malformed reads. Do not invent totals. |
| TUI-RUNTIME-R004.1 | `tests/test_precommit_hooks.py::test_spec_group_preserves_stages_and_trailer_fallback` | Group runs at commit, push and manual stages; explicit trailer fallback remains | Missing stage, fallback or retained blocking hook fails |
| TUI-RUNTIME-R012.4.1 | Command dispatcher with real AgentClient and recording transport | One named unavailable notice | No REST or mutation request for any management subcommand |

| TUI-RUNTIME-R004.2 | `tests/test_precommit_hooks.py::test_layout_and_surface_checks_follow_shared_advisory_policy` and `test_docs_ci_enforces_spec_checks_with_full_history_and_range` | Weekly checks and blocking spec CI cover documentation changes | Missing gate, shallow checkout, absent range or suppressed failure fails |

| TUI-RUNTIME-R012.4.3 | Planned remaining acceptance | Planned full command-matrix served fixture must cover every command family and make zero unserved-route requests. | Parent remains open until this proof passes |

| TUI-RUNTIME-R010.4.2 | Planned remaining acceptance | Planned served fixture must render the actual current scaffold and refuse missing, stale or other-caller state without reconstruction. | Parent remains open until this proof passes |

R002.1.3.2.2.3 HTTP acceptance also exercises legacy omission, both unavailable
reasons, null or incomplete data, unknown refusal reasons, invented cursors and
oversized projections. Every fixture observes tasks/get with the committed-event
opt-in; malformed projections refuse the complete snapshot.

R001.3 refusal and mocked dispatch tests remain regression coverage only. They
are not bound as full-criterion evidence. The signed A2A success, tamper, expiry,
replay and stale-lease fixture in the original matrix remains required.

TUI-RUNTIME-R002.1.6 covers root unary discovery, scoped fallback after 404/405,
credential preservation, malformed cards and refused discovery. A completed
history reply must render after exactly one message/send. These tests do not
qualify native prompt startup or model execution.

TUI-RUNTIME-R002.1.7 exercises unsupported codes -32010, -32004 and -32601.
Any raw result prevents fallback, including empty artifacts. HTTP 401/403 and
RPC permission refusals produce one failed stream request and no unary request.
Permitted fallback preserves message identity and the idempotency key.

## Source quality acceptance

| ID | Acceptance evidence |
|---|---|
| `TUI-RUNTIME-R015` | All child tests must pass through their owning production or tooling entry points. |
| `TUI-RUNTIME-R015.1` | Planned `tests/test_source_quality.py::test_source_quality_1` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.2` | Planned `tests/test_source_quality.py::test_source_quality_2` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.3` | Planned `tests/test_source_quality.py::test_source_quality_3` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.4` | Planned `tests/test_source_quality.py::test_source_quality_4` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.5` | Planned `tests/test_source_quality.py::test_source_quality_5` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.6` | Planned `tests/test_source_quality.py::test_source_quality_6` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.7` | Planned `tests/test_source_quality.py::test_source_quality_7` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.8` | Planned `tests/test_source_quality.py::test_source_quality_8` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.9` | Planned `tests/test_source_quality.py::test_source_quality_9` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.10` | Planned `tests/test_source_quality.py::test_source_quality_10` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.11` | Planned `tests/test_source_quality.py::test_source_quality_11` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.12` | Planned `tests/test_source_quality.py::test_source_quality_12` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.13` | Planned `tests/test_source_quality.py::test_source_quality_13` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.14` | Planned `tests/test_source_quality.py::test_source_quality_14` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.15` | Planned `tests/test_source_quality.py::test_source_quality_15` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.16` | Planned `tests/test_source_quality.py::test_source_quality_16` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.17` | Planned `tests/test_source_quality.py::test_source_quality_17` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.18` | Planned `tests/test_source_quality.py::test_source_quality_18` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.19` | Planned `tests/test_source_quality.py::test_source_quality_19` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.20` | Planned `tests/test_source_quality.py::test_source_quality_20` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.21` | Planned `tests/test_source_quality.py::test_source_quality_21` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.22` | Planned `tests/test_source_quality.py::test_source_quality_22` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.23` | Planned `tests/test_source_quality.py::test_source_quality_23` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.24` | Planned `tests/test_source_quality.py::test_source_quality_24` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.25` | Planned `tests/test_source_quality.py::test_source_quality_25` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.26` | Planned `tests/test_source_quality.py::test_source_quality_26` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.27` | Planned `tests/test_source_quality.py::test_source_quality_27` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.28` | Planned `tests/test_source_quality.py::test_source_quality_28` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.29` | Planned `tests/test_source_quality.py::test_source_quality_29` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.30` | Planned `tests/test_source_quality.py::test_source_quality_30` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.31` | Planned `tests/test_source_quality.py::test_source_quality_31` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.32` | Planned `tests/test_source_quality.py::test_source_quality_32` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.33` | Planned `tests/test_source_quality.py::test_source_quality_33` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.34` | Planned `tests/test_source_quality.py::test_source_quality_34` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.35` | Planned `tests/test_source_quality.py::test_source_quality_35` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.36` | Planned `tests/test_source_quality.py::test_source_quality_36` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.37` | Planned `tests/test_source_quality.py::test_source_quality_37` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.38` | Planned `tests/test_source_quality.py::test_source_quality_38` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.39` | Planned `tests/test_source_quality.py::test_source_quality_39` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.40` | Planned `tests/test_source_quality.py::test_source_quality_40` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.41` | Planned `tests/test_source_quality.py::test_source_quality_41` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.42` | Planned `tests/test_source_quality.py::test_source_quality_42` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.43` | `tests/test_source_quality.py::test_source_quality_43` parses the credential-free example and creates the production client with its loopback defaults. Counterexamples with missing values, remote URLs, credentials or shell execution must fail validation. |
| `TUI-RUNTIME-R015.44` | Planned `tests/test_source_quality.py::test_source_quality_44` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.45` | Planned `tests/test_source_quality.py::test_source_quality_45` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.46` | Planned `tests/test_source_quality.py::test_source_quality_46` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.47` | Planned `tests/test_source_quality.py::test_source_quality_47` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.48` | Planned `tests/test_source_quality.py::test_source_quality_48` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.49` | Planned `tests/test_source_quality.py::test_source_quality_49` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.50` | Planned `tests/test_source_quality.py::test_source_quality_50` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.51` | Planned `tests/test_source_quality.py::test_source_quality_51` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.52` | Planned `tests/test_source_quality.py::test_source_quality_52` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.53` | Planned `tests/test_source_quality.py::test_source_quality_53` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.54` | Planned `tests/test_source_quality.py::test_source_quality_54` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.55` | Planned `tests/test_source_quality.py::test_source_quality_55` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.56` | Planned `tests/test_source_quality.py::test_source_quality_56` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.57` | Planned `tests/test_source_quality.py::test_source_quality_57` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.58` | Planned `tests/test_source_quality.py::test_source_quality_58` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.59` | Planned `tests/test_source_quality.py::test_source_quality_59` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.60` | Planned `tests/test_source_quality.py::test_source_quality_60` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.61` | Planned `tests/test_source_quality.py::test_source_quality_61` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.62` | Planned `tests/test_source_quality.py::test_source_quality_62` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.63` | Planned `tests/test_source_quality.py::test_source_quality_63` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.64` | Planned `tests/test_source_quality.py::test_source_quality_64` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.65` | Planned `tests/test_source_quality.py::test_source_quality_65` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.66` | Planned `tests/test_source_quality.py::test_source_quality_66` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.67` | Planned `tests/test_source_quality.py::test_source_quality_67` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.68` | Planned `tests/test_source_quality.py::test_source_quality_68` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.69` | Planned `tests/test_source_quality.py::test_source_quality_69` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.70` | Planned `tests/test_source_quality.py::test_source_quality_entry_wiring` must enter the installed command against an authorized served fixture. |
| `TUI-RUNTIME-R015.71` | Planned `tests/test_source_quality.py::test_source_quality_served_entry` must enter the installed command against an authorized served fixture. |

### Native runtime palette switching (R008.2.3.2.1)

Pass unmodified F6 press events to the production palette handler and render
all four views with its style. Check palette order and wraparound, unknown-name
fallback, nonempty NO_COLOR, and unchanged scroll position. Repeated, released,
modified and unrelated keys must not change the palette. Switching must not
change pending reads, task state or modal confirmation; verify these dispatch
boundaries separately from the palette-handler tests. These focused tests do
not replace the remaining served parity and performance checks.

- `TUI-RUNTIME-R008.2.3.2.2`: Retain all parent served parity and release performance checks after baseline palette switching.
