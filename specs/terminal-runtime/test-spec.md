# TUI-RUNTIME test specification

| Requirement | Layer and fixture | Expected positive result | Required negative proof |
|---|---|---|---|
| TUI-RUNTIME-R001.1 | Unit command parser plus `httpx.MockTransport`; installed generated registry artifact | Known op and object params produce one versioned request with correct envelope | Empty ID, malformed JSON, array input, unknown op, missing registry file and digest mismatch make zero effect requests |
| TUI-RUNTIME-R001.2 | Client transport with loopback and remote URLs, fake bearer | Verified caller header reaches remote Arbora only over TLS | Remote HTTP, absent/invalid bearer, credential in exception/log/snapshot all fail |
| TUI-RUNTIME-R001.3 | A2A fake server issues a PLAN with binding and expiry. | One `/confirm` resumes exactly the issued plan. | Tampered op/input/digest/subject, expired plan and replay fail before effects. The server also rejects stale leases. |
| TUI-RUNTIME-R001.4 | Mock error envelope, timeout, disconnect and malformed JSON. | Typed success renders and chat remains functional. | Every failure renders an error. The session stays usable and never reports success. |
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

## Operator documentation and installed-entry receipt

R015.11, R015.14 and R015.17 now have installation instructions and a contributor guide.
The guide identifies tools, executable commands and source responsibilities.
Documentation contracts reject five installation mutations and three contributor-guide mutations.
Both positive documentation contracts fail against the unchanged main documentation at 612446cb.
A real `uv sync --frozen --offline` rejects a checkout without its lockfile.

On GR1080, Python 3.14.7 and uv 0.12.21 ran these documented commands successfully:

- `uv sync --frozen`
- `uv run --frozen tuig --help`
- `uv sync --frozen --extra test`
- `uv run --frozen --extra test pytest tests/test_source_quality.py -q`: 7 passed.

The commands used an isolated copy of tracked source and an external environment.
A wheel built with `uv build --wheel` was installed into a separate environment using exported lock constraints.
With TUI_TEST_INSTALLED_ENV set to that environment, R015.70's installed-entry test passed.
It runs outside the checkout, verifies installed metadata and import location, then invokes the real console script.
Help and invalid arguments make no recorded fixture GET or POST requests.
A valid headless prompt sends one message/send and renders the loopback fixture response.
The fixture is not an installed Arbora service and does not qualify authenticated denial or empty results.
Without TUI_TEST_INSTALLED_ENV, this test skips; that skip is not installed-entry proof.

The combined operator-documentation, installed-entry, source-quality, CLI-documentation and docs-layout suite passed 40 tests.
No runtime behavior, package version or dependency changed. R015.10 and R015.12 full documentation accuracy remain open.
Version-analysis requirements, R015.71 installed served behavior, native and release performance acceptance remain open.

## README navigation and architecture receipt

R015.13 adds navigation to every top-level README section. The existing native usage note now belongs to Usage, not License.
R015.15 explains the Python entry paths, shared client, A2A task flow and separate Arbora process.
Source links identify the entry module, application, headless driver, client, screens, widgets and separate Rust implementation.
Both documentation contracts reject the unchanged README at d6fb8293 because the required sections are absent.
Four navigation counterexamples reject missing, stale and duplicate targets.
Five architecture counterexamples reject wrong process boundaries, transport, source paths and implementation claims.
The source check confirms both Python consumers call the shared client factory.

On GR1080 with Python 3.14.7, this focused suite passed 54 tests:

```bash
python -m pytest tests/test_readme_navigation.py tests/test_operator_documentation.py tests/test_import_guard.py tests/test_cli_documentation.py tests/test_headless.py -q
```

Existing subprocess import guards verify that application and headless imports do not load the heavy backend.
The headless import guard also rejects a Textual import. Existing parser and headless tests cover dispatch, rendering and authentication.
These checks support the architecture explanation; they do not qualify all advertised features or full native parity.
R015.16 already has detailed-documentation links and receives no new completion credit.
R015.10 and R015.12 remain open. Other feature claims and the detailed architecture page still need a separate audit.
The exact-main qualification receipt from PR 137 remains the broad-suite baseline; this batch does not rerun that suite.
Its coroutine-finalization warning remains unresolved. Live-service, installed-service and release-performance acceptance remain open.

## Environment inventory receipt

R015.41.2 adds missing native task controls, terminal detection and shell selection to the configuration reference.
It documents all 24 dynamic schema aliases, exact-key precedence, empty values, coercion and expansion behavior.
The source audit covers direct Python getenv/environ reads and native env::var reads throughout both implementations.
Dynamic key lookups remain explicit; arbitrary inherited subprocess and dependency variables are not terminal configuration keys.
The inventory rejects unchanged documentation at bb988ba2, three new undocumented read patterns and three documentation mutations.

On GR1080 with Python 3.14.7, the following focused suite passed 79 tests:

```bash
python -m pytest tests/test_environment_inventory.py tests/test_notifications.py tests/test_cli_documentation.py -q
```

Tests exercise each uppercase schema alias, lowercase precedence, empty overrides, boolean and integer conversion, and literal environment strings.
A file-backed test proves environment, local TOML, global JSON and schema precedence, including removal of the environment override.
Existing notification and CLI tests support terminal detection and directory behavior.
No settings behavior, credential policy, native code or dependency changed.
This receipt documents lookup support; it does not prove that every setting changes runtime behavior.
Native source reads were audited against existing code. The exact-main receipt from PR 137 remains the broad Python/native baseline.
Its coroutine-finalization warning remains unresolved. Installed-service, live-service and release qualification remain open.

## Shared fixture settings isolation receipt

R015.37 repairs the shared pytest fixture, which previously isolated session data but left developer settings reachable.
The fixture now redirects global configuration and the default local settings file into each test directory.
Pytest restores the data/configuration environment and default settings paths after each test.
Explicit settings paths remain available to tests.

The regression copies the production conftest into a child pytest suite with disposable developer sentinel files.
Two child tests verify default isolation, persistence within one test, no cross-test leakage and explicit-path independence.
A session-finish check verifies restored environment and default settings path. Parent checks verify untouched sentinel files.
On unchanged main 36de5343, both child cases fail because the default settings path remains outside the test directory.
No real developer files are used in that counterexample.

GR1080 validation used Python 3.14.7 and the existing qualification environment with Arbora 0.1.7:

- The fixture, widget, settings/MCP, environment, mounted-command and CLI suite passed 280 tests.
- `PYTHONPATH=. python -m pytest tests -q -n 4 --tb=short` passed 1,720 tests, with four skips and six snapshots passed.
- The broad run reported no warning. This does not establish the cause or repair of PR 137's intermittent coroutine-finalization warning.

The initial older environment lacked Arbora and failed collection of the mounted-command module; no tests passed from that attempt.
The qualification environment was reused without dependency changes, under its existing no-deps Arbora policy.
The broad Python rerun was necessary because this autouse fixture affects the entire suite.
Native code did not change; the existing exact-main native receipt remains the baseline.
Skipped optional cases confer no new installed/native acceptance. R015.38 and broad assertion-quality requirements remain open.
No application runtime behavior or user configuration changed.

## Structure parity rows

| Requirement | Layer and fixture | Expected positive result | Required negative proof |
|---|---|---|---|
| TUI-RUNTIME-R003 | File-level unit test in `tests/test_skill_package.py` | Wheel contains the skill | Skill missing from wheel fails |
| TUI-RUNTIME-R004 | Child proofs in `tests/test_precommit_hooks.py` | Shared spec enforcement and weekly repository checks follow policy | Missing coverage or a nonblocking spec command fails |
| TUI-RUNTIME-R005 | File-level unit test in `tests/test_docs_layout.py` | Four pages exist and are in nav | A page absent from nav fails |
| TUI-RUNTIME-R006 | File-level unit test in `tests/test_precommit_hooks.py` | Both sections present | A missing section fails |
| TUI-RUNTIME-R007 | File-level unit test in `tests/test_docs_layout.py` | Workflow calls pipelines at main | A SHA pin fails |
| TUI-RUNTIME-R008 | File-level unit test in `tests/test_app_handlers.py` | Default theme and no-colour fallback hold | An unknown theme name falls back, not crashes |
| TUI-RUNTIME-R008.1 | Production native draw function with Ratatui TestBackend. | Resize from 100 to 40 columns preserves wrapped discovery status and complete keyboard help. Tokyo Night tokens render. | Nonempty NO_COLOR resets foreground and background. Unsupported AGENT_THEME falls back without panic. |
| TUI-RUNTIME-R009 | File-level unit test in `tests/test_docs_layout.py` | Four headings present | A missing heading fails |

## Cross-terminal presentation inventory

This inventory binds existing R008 rows without closing full presentation acceptance.

| Existing requirement | Evidence and remaining limits |
|---|---|
| R008 keyboard access | `test_presentation_resize.py` verifies sidebar reopening focuses its tabs, arrow navigation, resize and composer return. The baseline targets a non-focusable container. |
| R008.2.1 baseline tokens | Existing Python contrast tests and native presentation tests check the four baseline palettes. They do not qualify every accent/widget combination. |
| R008.2.2 viewport behavior | Native production viewport tests retain requested rows through refresh and resize. Mounted Python tests preserve a multiline draft and available reading space. |
| R008.2 retained parity | `test_presentation_pty.py` tests both production terminals against one loopback task fixture. It checks reading, paging, resize, theme redraw, visible-row retention through switching, color suppression and clean exit. Navigation makes no extra recorded POST requests. GET activity is not asserted. |

The PTY matrix uses 100x30 and 40x16 viewports, with and without nonempty NO_COLOR.
Python uses the actual module command; native uses an explicitly compiled current binary.
The fixture serves a unary task and an empty skills list. It is not installed Arbora or live backend qualification.
The test requires optional pyte and TUI_NATIVE_TEST_BINARY for native cases. Missing prerequisites skip those cases and do not count as passes.
Python keeps Textual monochrome behavior; native resets foreground/background. Empty NO_COLOR semantics still differ.
Full selection, all-view contrast, reduced-motion parity, served authentication and release performance remain open.

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
| p95 render | Send 10,000 events at 100/s. Measure adapter receipt to frame flush; include resize and key input. | p95 <= 50 ms, p99 <= 100 ms; no hidden drops |
| Multiple clients | Repeat with 1, 4 and 16 clients. Use shared and distinct principals. Include a slow reader and a disconnect. | Latency targets hold. No protected data crosses scope. Memory and queue limits hold. |

These are acceptance targets, not measured claims. If hardware cannot meet a
target, revise it with baseline evidence before acceptance. Report raw samples,
percentile method and failures; do not average away a slow client. Broker trials
must include broker RSS/CPU in totals. At 16 clients, require at least 20%
lower total RSS or upstream request count, with no latency regression. Otherwise keep
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

## Incumbent coding-terminal cutover evidence

Start from working incumbent-terminal skill access and Arbora connectivity. Keep that
installation available while testing the native terminal. In each client,
discover and invoke the maintained development skill. Run two Arbora-managed
agents concurrently and stream both tasks. Cancel one without affecting the other.
Disconnect and recover the surviving task with unchanged task/context/run IDs.
Exercise approval denial, expired confirmation and identity mismatch. No client
may grant an effect locally. Compare served results and refusal behavior at
recorded client and Arbora heads. Cutover requires operator acceptance after
parity and performance evidence. Verify the incumbent coding terminal remains a working rollback path.

## Native discovery tests (R002.7)

Run cargo test with the Tuig native manifest at `native/agent-terminal-ui/Cargo.toml` after slot allocation.
The discovery integration tests serve real loopback HTTP responses. They verify
the existing Agent Card route, caller header, invalid endpoint refusal,
authentication errors, redirects, malformed cards and cancellation during a
pending response. Renderer tests use the terminal buffer to verify refusal and
unavailable task actions. The size-limit case checks bounded input. A Linux pseudo-terminal smoke passed discovery, refusal/retry, cancellation and
terminal restoration. These fixtures are not a served Arbora deployment receipt.

## Native presentation acceptance remainder

TUI-RUNTIME-R008.2 remains pending. Test every supported theme, contrast, keyboard action, selection, scroll position and reduced-motion setting. Exercise the production native client against the declared presentation fixtures. Use the R002 render benchmark before acceptance. Discovery wrapping alone does not close this row.

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

- TUI-RUNTIME-R011.1: Planned `native/agent-terminal-ui/tests/coding_session.rs::test_session_model_closed_capability_set`. Unknown methods must map to a typed refusal.
- TUI-RUNTIME-R011.2: Planned `native/agent-terminal-ui/tests/coding_session.rs::test_capability_handlers_serve_local_host`. A read inside the root must return file text and prompt zero times.
- TUI-RUNTIME-R011.3: Planned `native/agent-terminal-ui/tests/coding_session.rs::test_path_containment_refuses_escape`. Parent segments, absolute paths and symlinks leaving the root must be refused with zero bytes read or written.
- TUI-RUNTIME-R011.4: Planned `native/agent-terminal-ui/tests/coding_session.rs::test_write_shows_diff_then_applies_on_approval`. A denied write must leave the file bytes unchanged.
- TUI-RUNTIME-R011.5: Planned `native/agent-terminal-ui/tests/coding_session.rs::test_command_displayed_before_run`. A denied command must spawn zero processes.
- TUI-RUNTIME-R011.6: Planned `native/agent-terminal-ui/tests/coding_session.rs::test_terminal_output_streams_in_order`. Output above the limit must carry the truncation marker and kill must end the process.
- TUI-RUNTIME-R011.7: Planned `native/agent-terminal-ui/tests/coding_session.rs::test_resume_reattaches_without_granting`. A resumed session must display the same pending write and apply no change before approval.
- TUI-RUNTIME-R011.8: Planned `native/agent-terminal-ui/tests/coding_session.rs::test_requests_reach_view_from_client_stream`. A request in the stream must reach `CodingSessionView` once.
- TUI-RUNTIME-R011.9: Planned `native/agent-terminal-ui/tests/coding_session.rs::test_entry_point_opens_session_at_cwd`. Starting in a temporary directory must send that root at `session/new`.
- TUI-RUNTIME-R011.10: Planned `native/agent-terminal-ui/tests/coding_session.rs::test_typed_refusals_reach_gateway`. Each reason must produce one error response and zero host effects.
- TUI-RUNTIME-R011.11: Planned `native/agent-terminal-ui/tests/coding_session.rs::test_evidence_record_has_no_secrets`. The record must carry the decision and omit file content.
- TUI-RUNTIME-R011.12: Planned `native/agent-terminal-ui/tests/coding_session.rs::test_headless_coding_session_write_and_containment`. The test must observe the diff, the approved write and the refusal.

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
Local HTTP tests cover current-plan-only registries with credentials and explicit no-auth mode.
They assert run-ID-only requests, unavailable summary fields and no fallback after a failed summary read.
Malformed or unavailable summaries clear protected values. Plan-only decoder tests cover expiry and empty plans.
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

| TUI-RUNTIME-R012.4.3.1 | Partial dispatcher and usage entry-point coverage | `tests/test_registered_command_contract.py` checks every handler signature and real mounted AgentApp keyboard focus dispatch. Focus commands start no model turn. Exact command names survive Enter unchanged; ambiguous prefixes cannot select a sibling. A unique partial name completes before submission. Mounted usage aliases use real HTTP transport fixtures. Full served command-family coverage remains pending. | These fixtures establish only this narrow child, not complete matrix or live producer acceptance |

| TUI-RUNTIME-R010.4.2 | Planned remaining acceptance | Planned served fixture must render the current scaffold and refuse missing, stale or other-caller state without reconstruction. | Parent remains open until this proof passes |

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
| `TUI-RUNTIME-R015.11` | `tests/test_operator_documentation.py::test_operator_installation_documentation`; see operator documentation receipt above. |
| `TUI-RUNTIME-R015.12` | `tests/test_operator_documentation.py::test_readme_operator_entry_points` and negative cases; see operator package qualification receipt. |
| `TUI-RUNTIME-R015.13` | `tests/test_readme_navigation.py::test_readme_navigation_reaches_each_top_level_section` and counterexamples; see README navigation and architecture receipt. |
| `TUI-RUNTIME-R015.14` | `tests/test_operator_documentation.py::test_locked_install_refuses_a_checkout_without_its_lockfile`; see operator documentation receipt above. |
| `TUI-RUNTIME-R015.15` | `tests/test_readme_navigation.py::test_readme_explains_frontend_entry_paths_and_served_boundary` and counterexamples; see README navigation and architecture receipt. |
| `TUI-RUNTIME-R015.16` | `tests/test_operator_documentation.py::test_readme_links_existing_detailed_documentation` and negative cases; see operator package qualification receipt. |
| `TUI-RUNTIME-R015.17` | `tests/test_operator_documentation.py::test_contributor_guide_tools_commands_and_source_map`; see operator documentation receipt above. |
| `TUI-RUNTIME-R015.18` | `tests/test_package_metadata.py::test_declared_mit_license_is_tracked_and_linked` and negative cases; see operator package qualification receipt. |
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
| `TUI-RUNTIME-R015.31` | Partial Python bump and native consistency checks in `tests/test_package_metadata.py`; native version-configuration coverage remains open. |
| `TUI-RUNTIME-R015.32` | `tests/test_historical_analysis.py` verifies the original JSON report bytes in immutable Git history and refuses changed bytes or release-mirror registration. Full Git history is required for preservation acceptance. |
| `TUI-RUNTIME-R015.33` | `tests/test_historical_analysis.py` verifies the original Markdown report bytes in immutable Git history and refuses changed bytes or release-mirror registration. Full Git history is required for preservation acceptance. |
| `TUI-RUNTIME-R015.34` | Planned `tests/test_source_quality.py::test_source_quality_34` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.35` | Planned `tests/test_source_quality.py::test_source_quality_35` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.36` | Planned `tests/test_source_quality.py::test_source_quality_36` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.37` | `tests/test_fixture_isolation.py` runs the production shared fixture in a child pytest process; developer sentinels stay unchanged and test state resets. |
| `TUI-RUNTIME-R015.38` | Planned `tests/test_source_quality.py::test_source_quality_38` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.39` | Planned `tests/test_source_quality.py::test_source_quality_39` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.40` | Planned `tests/test_source_quality.py::test_source_quality_40` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.41` | Planned `tests/test_source_quality.py::test_source_quality_41` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.42` | Planned `tests/test_source_quality.py::test_source_quality_42` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.43` | `tests/test_source_quality.py::test_source_quality_43` parses the credential-free example and creates the production client with its loopback defaults. Counterexamples with missing values, remote URLs, credentials or shell execution must fail validation. |
| `TUI-RUNTIME-R015.44` | Production get_mcp_config: authenticated fleet.status success/empty and malformed children; no raw configuration claim. |
| `TUI-RUNTIME-R015.45` | Production list_mcp_tools: authenticated catalog reads, opaque cursor preservation, bounds, cycles and failure after a partial page. |
| `TUI-RUNTIME-R015.46` | Production list_history_tasks: task/context identities, caller headers, opaque page reads and identity/bounds refusal. No complete enumeration or resume claim. |
| `TUI-RUNTIME-R015.47` | Production read failure matrix: empty success differs from denied, unavailable, malformed, disconnected and timed-out reads; active context stays unchanged. |
| `TUI-RUNTIME-R015.48` | Actual configured all-file hooks, including Ruff and mypy, must pass at the batch candidate; record execution below. |
| `TUI-RUNTIME-R015.49` | Production signature assertions plus actual configured mypy execution; signature presence alone is not type correctness. |
| `TUI-RUNTIME-R015.50` | tests/test_client_read_contracts.py exercises all three production read contracts through HTTP fixtures, alongside existing client and mounted tests. |
| `TUI-RUNTIME-R015.51` | The client maintenance batch receipt below records adapters, tests, completed gates and residual acceptance. |
| `TUI-RUNTIME-R015.52` | Fresh bounded client and mounted test execution plus configured all-file maintenance gates; record commands and results below. |
| `TUI-RUNTIME-R015.53` | Planned `tests/test_source_quality.py::test_source_quality_53` must enter the owning path and prove the requirement. |
| `TUI-RUNTIME-R015.54` | Source-linked assessment below, with the current environment example and production client refusal checked against its claims. Remaining served authority and coding-session requirements stay open. |
| `TUI-RUNTIME-R015.55` | Run project checks in the quality acceptance v1 matrix. Record the complete tracked-file scope and every finding. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.56` | Measure the full source and test tree against R015.1–R015.7, R015.19–R015.20 and R015.34–R015.35. A changed-file baseline does not prove acceptance. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.57` | Run source, secret and dependency scans. Retain raw reports, database dates and all severities; resolve every actionable finding. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.58` | Measure covered Python package lines and branches separately across the complete suite. Inventory native coverage separately; heuristic scores and test counts do not qualify. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.59` | Build documentation strictly, check links and examples, and run operator-documentation acceptance tests. Missing checks remain open. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.60` | Run boundary and dependency-seam tests against production imports and entry points. Record the full module responsibility map and unresolved violations. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.61` | Reconcile all declarations, implementation references and test bindings. Run spec and concept checks; resolve every orphan and missing binding. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.62` | Run both all-file stages with exact configured pins. Failures, warnings, skipped hooks and unavailable dependencies prevent acceptance. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.63` | Record collection, execution and outcomes for every test. Explain skips and expected failures; missing required acceptance coverage prevents acceptance. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.64` | Run version dry-run, lock consistency and installed-version checks. Preserve historical reports outside authoritative version mirrors. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.65` | Check the complete test inventory, shared fixtures, structural limits and behavior-specific assertions. Exercise incorrect results; assertion counts alone do not qualify. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.66` | Reconcile all Python, native and dynamic inputs with documented defaults and examples. Run environment, theme and log refusal tests. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.67` | Require passing evidence for R015.55–R015.66, all 17 domain entries and the current finding inventory. Missing evidence prevents acceptance. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.68` | Use the complete domain matrix in test-spec.md. Each domain needs completed checks and explicit remaining gaps; a grade is insufficient. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.69` | Reconcile historical priorities with current scan findings by stable identifier. Require resolution evidence for each item; never infer closure from a count. See quality acceptance v1 below; this amendment supplies no result receipt. |
| `TUI-RUNTIME-R015.70` | `tests/test_installed_operator_entry.py::test_source_quality_entry_wiring` runs the installed command against a loopback unary fixture; installed Arbora qualification remains open. |
| `TUI-RUNTIME-R015.71` | `tests/test_installed_operator_entry.py::test_installed_observer_distinguishes_denied_and_empty_reads` and negative cases; see operator package qualification receipt. |

### Native runtime palette switching (R008.2.3.2.1)

Pass unmodified F6 press events to the production palette handler and render
all four views with its style. Check palette order and wraparound, unknown-name
fallback, nonempty NO_COLOR, and unchanged scroll position. Repeated, released,
modified and unrelated keys must not change the palette. Switching must not
change pending reads, task state or modal confirmation; verify these dispatch
boundaries separately from the palette-handler tests. These focused tests do
not replace the remaining served parity and performance checks.

- `TUI-RUNTIME-R008.2.3.2.2`: Retain all parent served parity and release performance checks after baseline palette switching.

## Model-choice boundary and served acceptance

| Requirement | Layer and fixture | Expected positive result | Required negative proof |
|---|---|---|---|
| TUI-RUNTIME-R012.2 | Rollup of R012.2.1 and R012.2.2. | Both legacy client regression coverage and governed served model choice meet their child criteria. | Legacy reads and selection refusal alone cannot close model-choice acceptance. |
| TUI-RUNTIME-R012.2.1 | `tests/test_tui_widgets.py::TestModelConfiguration::test_model_registry_metadata_crosses_client_boundary` and `test_model_registry_failure_does_not_reuse_or_route`; Real AgentClient with HTTP fixtures. | Registry metadata survives authenticated GET /models unchanged. | After success, missing or denied routes, invalid JSON, non-object responses and timeouts raise errors. No stale data or alternate requests. |
| TUI-RUNTIME-R012.2.2 | Planned served fixture through the model picker, /model and the real client; actual models.list operation from ARBORA-A2A-R016.6 | Discover profiles, send arboraModelProfile preference and display the producer-selected profile from task metadata | When Arbora does not honour the preference, display its different selected profile without local model routing. Legacy reads and selection refusal are not evidence for this child |

- `TUI-RUNTIME-R012.3.1`: `tests/test_task_history.py` covers bounded task pages, two contexts, fresh-client reply reads, refusal, missing replies and read-only mounted browsing.
- `TUI-RUNTIME-R012.3.2`: Retain the parent served two-context, prior-turn, restart, continuation and foreign-context acceptance.
## Bounded native reply and metadata contracts

- `TUI-RUNTIME-R002.1.3.2.2.2.1`: Task output parser, HTTP and production renderer tests cover bounds, malformed parts, unavailable output and clearing.
- `TUI-RUNTIME-R008.2.3.2.2.3`: Production viewport tests check wrapped row movement, refresh restoration and boundary clamping.
- `TUI-RUNTIME-R012.6.1`: Usage parser, HTTP and renderer tests cover binding, malformed counters, zero versus missing, valid reply preservation and clearing.
- `TUI-RUNTIME-R002.1.3.2.2.2.2`: Submission HTTP and argument tests check queue delay beyond the read deadline, configured bounds, unknown timeout and no resend.
- `TUI-RUNTIME-R002.1.3.2.2.2.3`: Argument and authenticated HTTP tests check default omission, explicit opt-in, unavailable evidence and refusal without retry.

These local contracts do not close full served recovery, presentation parity or usage.read session cost acceptance.

- `TUI-RUNTIME-R002.1.3.2.2.2.4`: Remaining served stream recovery acceptance. Full served receipts remain required; local unary tests cannot close this row.
- `TUI-RUNTIME-R008.2.3.2.2.4`: Remaining served presentation qualification. Full served parity and release performance receipts remain required.
- `TUI-RUNTIME-R012.6.2`: Served turn and session token and cost display. A served fixture renders turn and session totals and unavailable values after operation refusal.
## Shared development guard consumer

| Requirement | Layer and fixture | Expected positive result | Required negative proof |
|---|---|---|---|
| TUI-RUNTIME-R015.29.1 | `tests/test_shared_hook_consumers.py` and actual remote pre-commit installs | Exact pins preserve both stages and invocation flags. A clean linked worktree passes. | Altered configuration fails. Real hooks reject legacy markers, canonical edits and foreign Cargo targets. |

## Modal keyboard ownership

Partial R008 evidence exercises the mounted exit, graph-chat and tool-approval
journeys in `tests/test_modal_keyboard_isolation.py`. Escape returns to the
composer; Shift+Tab moves focus without changing the agent mode. Input editing
keys stay with the modal, including Ctrl+A, Ctrl+C, Ctrl+D, Ctrl+U and Ctrl+Y.
Escape denies pending approvals through the existing callback. The fixture
checks main-screen shortcuts separately. Transport effects are not qualified.
Full presentation, native parity and served acceptance remain open.

## Settings and MCP viewport access

`tests/test_settings_mcp_layout.py` records partial R008 accessibility evidence.
Mounted AgentApp journeys resize from 120x40 to 40x12, 60x20 and back.
Settings search retains text and focus. Tab reaches the filtered checkbox, and Space persists its changed value.
A focused field near the end of the unfiltered form remains visible after resize.
The settings screen is mounted directly because no application command exposes it.
The MCP journey enters `/mcp`, navigates thirty fixture tools, and retains the selected cell inside the resized table.
Both dialogs keep their controls within their bounds. MCP resize reveals the selected cell after layout settles.
Escape restores composer focus. Reopening settings retains the saved value; reopening MCP handles an empty catalog.
These fixtures do not qualify live catalog transport, native parity, PTY behavior or release performance.
R008 and its remaining full presentation acceptance stay open.

## Python operator documentation

`tests/test_cli_documentation.py` captures actual CLI help and tests dispatch.
It rejects invalid observer combinations and checks documented directory precedence.
Existing theme fallback and mounted log refusal tests remain behavior evidence.
These tests do not prove model selection, history loading or backend authority.

## Canonical run-inspection consumer evidence

`tests/test_run_inspector_contract.py` enters the generated `runs.get` and
`runs.events` paths through the real client and mounted inspector. It covers
strict overview identity, old-client refusal, exact requests, literal payloads
and bounded replay. It also covers denial clearing and stale reads after
refresh, close or owner changes. Owner changes before mount issue no request. Row and follow
events before idle clear paused or completed views. The command matrix covers
explicit run aliases and no-ID refusal without legacy requests.
`/run plan` retains its separate tests.
Current-contract transport cases inject two schema lookups from the pinned
`tests/fixtures/public_run_operations.json` fixture. Its source is Arbora
`45b8d1d8bae4e3621f9432030769803a659671fc`. The installed invoker, digest check
and HTTP transport remain unchanged. This seam does not alter the production
SDK or its operation enum. Separate tests use the untouched installed SDK to
verify missing operations refuse before HTTP. Those tests skip when the local
SDK already includes the operations; skips are not old-release acceptance.
This is partial evidence for R010.1, R010.6 and R012.4.3.2. Full harness fields,
released-stack and live producer acceptance remain open.

## Unsupported image input boundary

- `TUI-RUNTIME-R012.5.1`: `tests/test_commands.py::TestImageCommand::test_cmd_image_refuses_without_reading` proves that empty, quoted, missing and malformed paths receive an unsupported notice with no reads or pending-part changes. `tests/test_client.py::test_image_command_refusal_preserves_next_text_submission` uses the real command, application part collector and client to prove the next text turn still submits existing text attachments. `test_non_text_parts_are_refused_before_any_request` rejects typed, legacy untyped, mixed and malformed unsupported parts before network access.

### Bounded text-file evidence

`tests/test_text_files.py` covers `/file` staging, names, removal, quoted paths,
invalid content, regular-file checks, owner changes and queued dispatch.
`tests/test_client.py` proves exact file payloads through the existing stream and
poll paths, inclusive limits, zero-request refusal and server upload errors.
These fixtures extend R012.5.2 without closing its served PNG and pasted-image
criteria. The attachment rollup remains open.
- `TUI-RUNTIME-R012.5.2`: Retain the served PNG admission and oversized-file criteria. Refusing every image without reading it is not file-size validation or successful image admission.

## Nonblocking unary polling

`TUI-RUNTIME-R012.1.1`: Protocol fixtures assert configuration.blocking=false, one submission, bound identity, terminal artifacts, failure, cancellation, refusal and timeout. These tests do not prove served streaming or active-crash resume.

`TUI-RUNTIME-R012.1.3`: Native submission protocol checks the nonblocking flag. UI observation tests cover active and terminal snapshots, identity mismatch, deadline expiry and cancellation confirmation. These local tests are not installed-backend acceptance.

## TUI-RUNTIME-R002.1.3.3: anonymous native task transport

- Explicit none mode sends no Authorization header for submit, read and cancel.
- Default submission and observation without a bearer still make zero requests.
- None mode rejects a bearer, remote HTTP/HTTPS, URL credentials and invalid modes.
- Redirects and auth refusals do not trigger retries or downgrade.
- Anonymous task clients cannot obtain authenticated host-log authority.
- Observe remains read-only in the actual loopback EG/Arbora/native journey.

## Responsive modal layouts

Partial R008 presentation evidence covers chat-dialog bounds, approval-list
scrolling, visible compact approval controls, and feedback focus after resize.
`tests/test_modal_layout.py` resizes the same mounted modal through 120x40,
40x12 and 60x20 viewports, then restores 120x40. The baseline clips the chat
dialog, hides approval feedback and clips one-row button content. These local
fixtures do not close native parity, full keyboard access, served journeys or
performance acceptance. R008 and its remaining presentation leaf stay open.

## Collapsed public-detail regression proof

- R012.1.4: mount the actual Conversation and ToolCallBlock. Focus the header,
  press Enter/Space and click. Stream late and replacement output. Verify
  visible content and preserved explicit choice for every tool_expand setting.
- R008.2.3.2.2.1: drive the actual Python and native public event views with the
  same fixture. Verify default collapse, independent summary/trace labels,
  keyboard and mouse selection, and replay/reconnect choice retention.
  Check bounded reads, refusal clearing and suppression of unrecognized/private fields.
  Run tests/test_native_public_details_pty.py with TUI_NATIVE_TEST_BINARY for
  real native keyboard, mouse, refresh and quit evidence over local HTTP.
- R008.2.3.2.2.2 and R012.1.2 retain full served and release qualification.

### Whole-app public-fold keyboard qualification

R008.2.3.2.2.2.1 requires a keyboard route from the composer to the conversation
without replacing Tab completion or Shift+Tab focus navigation. F8 switches focus
between conversation and composer. Tab reaches public fold titles; Enter and
Space toggle them. Refresh preserves focus and fold state. This focused check
does not close the remaining presentation or release-performance criteria.

R008.2.3.2.2.2.2 retains complete tokens, selection, keyboard parity, no-color,
reduced motion, served journeys and release performance. The parent stays open.

| TUI-RUNTIME-R012.4.3.2 | Retained complete acceptance | Planned full command-matrix served fixture covers every command family with zero unserved-route requests. | Remains open until full proof passes |

## TUI-RUNTIME-R012.3.1: Refresh task history

Mounted command tests press R to refresh the first server page. Fresh task
states replace old rows, prior replies clear, and pagination can reuse the
new page cursor. Denied and malformed refreshes clear old content; R retries.
Empty pages remain distinct from failed reads. Repeated R presses during a
pending read issue no extra request. All calls use tasks/list or tasks/get,
without changing the active context or resuming a conversation.

Branch evidence: five mounted refresh cases fail at base 9da41811 and pass
with the shortcut. The history-refresh, task-history and registered-command
suites pass 113 tests with two workers. All-files pre-commit passes. Canonical
status records local commit evidence; independent review and merge remain
pending. This does not close R012.3 conversation resume or live producer proof.

Close-during-refresh regression: a controlled HTTP transport suppresses
cancellation after Esc, then returns a page or denial. Both paths must leave
the closed screen's page and reply unchanged, without WorkerFailed or widget
lookups. The mounted flag alone is insufficient during Textual teardown.

Review correction evidence: both late-completion cases fail at 42f3875 with
WorkerFailed. They pass with the cancellation guard before page assignment or
widget updates. The same three focused suites now pass 115 tests with two
workers. All-files pre-commit passes. Independent re-review remains pending.
## TUI-RUNTIME-R012.4.2: Usage refresh ordering

A mounted UsageScreen with the real AgentClient and controlled HTTP transport
must reject late replies from cancelled reads. A newer denial, empty totals,
unknown totals or measured zero must remain visible after an older success or
error completes. Unknown values must not become zero. This client fixture does
not qualify live usage producers or close R012.6.

Local branch validation: all eight race cases fail at base 9da41811 and pass
with the worker guard. The focused usage, registered-command, current-plan and
public-run keyboard suites pass 122 tests with two workers. All-files pre-commit
passes. Generated commit evidence is local until independent review and merge;
R012.6 and full served command acceptance remain open.
## TUI-RUNTIME-R012.4.3.3: Unsupported command entry points

`tests/test_unavailable_session_commands.py` mounts the production AgentApp.
Enter submits /bg, /attach and /fast, including argument variants. Alt+O follows
the same refusal path as /fast. Require one unavailable warning, no session
manager access, unchanged identity and queue, no fast-mode flag and no model
turn. Existing focus and exact-command regressions must remain green.
This is client fixture evidence, not served scheduling or resume acceptance.

Command inventory at base `9da41811fe661c3920834cbf1313de51a5aeab09`:

- Client controls: help, clear, exit/quit, theme, queue variants, focus,
  keybindings and export. Focus and exact-command keyboard proofs exist.
- Served reads and invocation: model, history, fleet, mcp/tools, usage aliases,
  op/confirm, capability aliases and run aliases. Full mounted command coverage
  remains open, including inspector entry and refresh against served producers.
- Explicit refusal: image, skills, prompts, kb, cron, pipeline, mcp:reload;
  this slice adds truthful bg, attach and fast paths.
- Retained audit: plan/chat/build, init/review/test/search, compact/diff/recap,
  memory, agents, goal variants, simplify/add-dir, graph/ask/nl/obs/broker/kvcache,
  ingest, sdd, impact/codemap/resources, maintenance/config/logs. Existing handler
  tests do not establish full served acceptance for these families.

Branch validation for R012.4.3.3 passed 179 focused tests and the all-files
pre-commit gate. The canonical status tool records local commit evidence as
VERIFIED. This branch receipt is not default-branch delivery or live backend
acceptance; the task remains pending independent review and merge.

### Native held-key navigation

TUI-RUNTIME-R008.2.3.2.2.2.2.1 binds the production event filter to viewport
movement tests. Repeated action keys, modified navigation and release events
must be rejected; ordinary presses remain accepted. These local tests do not
prove live backend acceptance or the retained full presentation qualification.

### Native mouse-wheel navigation

TUI-RUNTIME-R008.2.3.2.2.2.2.2.1 uses the production mouse dispatcher and
Ratatui buffers to verify that only the visible viewport scrolls and folds retain
selection and expansion. Viewport tests cover both bounds, empty content,
refresh and resize retention. Modified and horizontal wheel events are inert;
cancellation confirmation blocks mouse navigation. No live backend acceptance
is claimed by these local tests.

### Merged delivery receipts

These receipts supersede the earlier branch-pending notes for their narrow
slices. Each reconciled head passed full CI, native checks and Python 3.12
compatibility before merge. Broader served and release requirements remain open.

| Slice | PR | Main merge |
|---|---|---|
| Command honesty | #110 | 5f78122fa16a35af5592b8cfd36e90318e4ce987 |
| Usage refresh ordering | #111 | 0118466743c78434120af64aefb1c47ecd47d96f |
| History refresh and close guards | #112 | 623935149142c8640f62f3290e0d5f0951fd4f32 |
| Native held-key navigation | #113 | 6f655fc3a657241eb5e1ce3625fb4b53cc56408c |

Wheel navigation remains pending main-targeted full/native CI and merge in #114.

### Previous task page navigation

TUI-RUNTIME-R012.3.1.1 extends the read-only Python task browser. Mounted
HTTP-fixture coverage in `tests/test_history_navigation.py` checks fresh
forward/back/forward reads, opaque cursor reuse, empty pages, refusal and
retry, cursor cycles, refresh reset, and duplicate input during reads. The screen discards late
success and error completions after close, even when the transport suppresses
cancellation. Active conversation identity remains unchanged.

The initial previous-page regression failed on main: P left task three visible
instead of rereading task two. These tests use a mock HTTP transport with the
production client and mounted app. They do not prove live backend acceptance
or complete history and conversation resume.

Independent review returned GO with no blocking findings and 38 passing history
tests. The combined history, command and usage suite passed 186 tests with two
workers. All-file gates passed. Publication remains with the coordinating parent.

### Native inspector search

TUI-RUNTIME-R010.10 tests Ctrl+F input ownership before global action letters,
case-insensitive matching lines, first-row reveal, reverse-video selection,
forward/backward wraparound and bounded Unicode editing. Recompute results
from the live inspector text so expired/refused values cannot remain in search.
Close and binding changes discard the query. No live backend acceptance claim.

### Client maintenance evidence batch

Base: `76a3655d42fa4d1643187d54a83cc8efd0cbbaf0`. Scope: existing R015.44–52.
This batch adds no child requirements.

| Adapter | Contract and evidence |
|---|---|
| `AgentClient.get_mcp_config` | `fleet.status` returns caller-visible children. Tests distinguish valid empty children from refusal and malformed fields. It does not return raw MCP configuration. |
| `AgentClient.list_mcp_tools` | `fleet.catalog.list` uses opaque cursors, 100 items per page and at most ten pages. Tests reject partial success after denial, timeout, malformed data or cycles. |
| `AgentClient.list_history_tasks` | `tasks/list` supplies bounded task pages with context identifiers. Tests retain repeated context IDs, validate identities and preserve active context. The client infers no complete context grouping or enumeration. |

`tests/test_client_read_contracts.py` uses the production client and generated
Arbora invoker with HTTP fixtures. It preserves the client's configured caller
header rather than supplying credentials inside the transport handler. The
fixture returns counterexamples for each read contract. Existing mounted
history and usage tests cover stale content and asynchronous lifecycle.

R015.46 concerns identifiers available through the current authorized contract.
R012.3 and R012.3.2 remain open for complete conversation history and resume.
R012.4.3, R012.6 and installed/live acceptance also remain open. These fixtures
prove consumer behavior, not backend authorization enforcement or live producers.

Validation: Python 3.14.7, frozen lock dependencies and official `arbora==0.1.7`.
The following command passed 209 tests with two workers, including 44 new cases:

```bash
.venv/bin/pytest tests/test_client_read_contracts.py tests/test_client.py tests/test_client_methods.py tests/test_served_fleet_usage.py tests/test_task_history.py tests/test_history_refresh.py tests/test_history_navigation.py -q -n 2
```

The configured all-file gate runs Ruff, mypy, Vulture, Bandit, canonical spec
checks and repository maintenance checks. Its first pass found two prose
issues. Stronger value assertions then exposed a test annotation error.
The batch fixes these findings without suppression. The final all-file gate passed, including Ruff and mypy:

```bash
PYTEST_XDIST_AUTO_NUM_WORKERS=2 pre-commit run --all-files
```

Independent review returned GO on scope and tests and reproduced 209 passing
tests with two workers. R015.46 covers bounded context identifiers only.
At this baseline, R015.48, R015.51 and R015.52 relied on execution and documentation receipts,
not artificial test markers. The trailer gate required bound tests, so these three rows remained open.
This batch added no artificial markers to change their generated state. No native build or live service was needed.

Candidate implementation: `20e00677ac4ccb15d813e4eb9a71a9155d3b8543`.
Six existing rows qualify through tests: R015.44, .45, .46, .47, .49 and .50.
R015.48, .51 and .52 retained execution receipts but remained open at this baseline.
The later client maintenance qualification below owns R015.48 and R015.51. R015.52 remains open.

## Theme keyboard regression (R015.53)

`tests/test_theme_keyboard.py::test_theme_shortcut_cycles_without_changing_composer`
presses Alt+Shift+T through the mounted AgentApp. It checks every registered theme
and wraparound, unchanged composer text and focus, and preserved no-color mode.
Both parameter cases fail on main at `52bc92d5` because the binding is absent.
This fixture does not qualify full native presentation or served performance.

## Native CLI help

`TUI-RUNTIME-R015.30.2`: `native/agent-terminal-ui/tests/cli_help.rs` runs the
actual native executable without a terminal. Both help aliases return the same
usage, supported flags and environment settings, including with invalid runtime
configuration. Mixed help/operation flags fail. A prompt value of `--help` still
reaches submission credential validation. These checks do not claim served
transport, native release or full terminal cutover qualification.

## Exit-modal keyboard access

Partial evidence for TUI-RUNTIME-R008.2.3.2.2.2.2.2.2:
`tests/test_exit_confirm_keyboard.py` checks all four arrow keys and cyclic focus.
It checks Space activation exactly once and the production Ctrl+D cancellation path.
Space, Enter and N preserve the unfinished composer text and restore focus.
The arrow and Space cases fail before the handler repair. This bounded change
does not close full keyboard parity, native presentation, served journeys or
release performance acceptance. The owning requirement remains open.
The application priority Escape/rewind binding still intercepts modal Escape.
That separate application binding conflict is not repaired by this widget change.

## Public detail malformed-binding regression

`TUI-RUNTIME-R008.2.3.2.2.1` clears the displayed task's protected summary and
trace when a replacement context or run identifier is malformed. It retains
fold choice and focus, leaves other tasks unchanged, and refuses replay until
the exact binding is validated again. This repairs the existing leaf; it adds
no new completed requirement or served acceptance claim.

Baseline: `52bc92d5fb1e140c9502f634b3ea6ac3c37f5760` on GR1080.
The seven parameter cases in
`tests/test_public_run_details.py::test_malformed_rebinding_clears_only_matching_task_and_requires_revalidation`
fail against unchanged baseline production code and pass with the repair.
The focused public-details, whole-app keyboard and mounted tool-block suite
passes all 106 tests with Python 3.14.7:

```bash
python -m pytest tests/test_public_run_details.py tests/test_public_run_keyboard_app.py tests/test_tool_call_block_mounted.py -q -o addopts='' --timeout=30 --timeout-method=thread
```

`pre-commit run --all-files` passes all configured commit-stage checks.
An isolated pre-commit cache avoids a missing manifest in the shared cache.
The restricted execution environment stalled mounted tests; the completed
results above use the same GR1080 host outside that restriction. No native,
live Arbora, release-performance or cross-terminal qualification is claimed.


The full pre-push gate passed every hook except pytest. Its default locked
all-extras environment lacks the optional Arbora client. It reported 1272
passes, one skip, seven failures in `tests/test_client.py`, and four collection
errors in `test_client_read_contracts.py`, `test_current_plan_view.py`,
`test_registered_command_contract.py` and `test_served_fleet_usage.py`.
A separate `uv run --all-extras` environment tests the same five files on unchanged main.
It reproduces all seven failures and four errors, with 74 passes.
This default gate remains failing. The repair changes no dependency or hook configuration.


The full suite also ran with the existing installed `arbora==0.1.7` client
environment on GR1080: 1444 passed, one skipped, and all six snapshots passed.
The command was `python -m pytest tests -q -n 2 --dist loadfile -p no:randomly -m 'not slow' --timeout=60 --tb=short`.
This installed-client result does not make the default pre-push environment green.


Publication rebase: `d370244d768458262cfc46692152eadd913709a2` adds native CLI help.
Both appended evidence sections are retained. Python production code is unchanged
by that upstream change. The full-suite receipt above predates this rebase.

## Empty tool output after display filtering

`TUI-RUNTIME-R012.1.4` determines initial fold availability from filtered content
and details. Control-only output renders empty and must remain inert. Pressing
Enter cannot record a user fold choice until visible content exists. Later
visible output still follows the configured expansion policy and retains focus.

Baseline: `d370244d768458262cfc46692152eadd913709a2` on GR1080.
The nine cases in
`tests/test_tool_call_block_mounted.py::test_control_only_initial_output_is_inert_until_visible_content_arrives`
fail before the production repair. They cover content, details and both fields
under always, on-fail and on-success policies. The repair passes all 108 tests
across the mounted tool, public-details and whole-app keyboard suites:

```bash
python -m pytest tests/test_tool_call_block_mounted.py tests/test_public_run_details.py tests/test_public_run_keyboard_app.py -q -n 2 --timeout=30 --timeout-method=thread
```

This repairs an existing leaf. It adds no completed requirement and makes no
served streaming, native presentation or release-performance claim.


Full-suite receipt before the publication rebase: Python 3.14.7 with installed
`arbora==0.1.7` passes 1446 tests, skips one, and passes all six snapshots.
The command is `python -m pytest tests -q -n 2 --dist loadfile -p no:randomly -m 'not slow' --timeout=60 --tb=short`.

The normal pre-push gate runs with two workers. All hooks except pytest pass.
Its locked all-extras environment lacks Arbora: 1274 pass, one skips, seven fail,
and four modules fail collection. The seven failures are in `test_client.py`.
Collection fails in `test_client_read_contracts.py`, `test_current_plan_view.py`,
`test_registered_command_contract.py` and `test_served_fleet_usage.py`.
The same five files on unchanged `d370244` reproduce seven failures and four
errors, with 74 passes. The repair changes no dependency or hook configuration.

The publication rebase includes merged PR #120 from `5643d81`.
Both evidence sections and task updates are retained. Full-suite counts above
predate this rebase; focused presentation tests and commit gates run again.

## Operation argument parsing

`TUI-RUNTIME-R001.1`: `tests/test_op_command_parsing.py` enters the production
dispatcher. Spaces, tabs and line breaks separate the operation and JSON without
changing string values. Malformed objects, nested NaN or Infinity constants and
non-object JSON cause one warning and zero client calls. A later valid command
still works. Missing IDs refuse; omitted parameters remain an empty object.
These tests use a client double and do not qualify generated registry validation,
versioned transport or served effects.
## Consistent command completion

`TUI-RUNTIME-R012.4.3.1`: `tests/test_command_completion_contract.py` mounts the
production composer and drives Enter and Tab. Exact command names retain their
identity instead of expanding to longer siblings. Case-insensitive prefixes and
aliases select one canonical command consistently across completion and the
suggestion list. Ambiguous prefixes and argument text are not replaced on Enter.
These keyboard fixtures do not claim the full served command matrix.

### Mounted command inventory and fleet dispatch

R012.4.2 now routes `/fleet` and `/fleet status` through the generated
`fleet.status` read. Empty children remain a successful response; malformed
children and refused reads display one named unavailable notice. The command does
not invent an approval count. Grant and invalid subcommands refuse before
transport. `/help` uses the registered TUI handlers and identifies the existing
unavailable operation families, without importing optional cross-surface help.

`tests/test_mounted_command_matrix.py` drives the actual AgentApp composer with
a real AgentClient and controlled HTTP responses. Its inventory accounts for
every registered command. This is client fixture evidence, not a live producer
or complete subcommand proof for R012.4.3.2; that row stays open.

| Command group | Mounted evidence and limit |
| --- | --- |
| help | All registered names, local descriptions and unavailable operation names |
| fleet | Status success, empty, malformed and refused; invalid arguments and grant do not dispatch |
| mcp, tools, usage/stats/cost/context | Generated read routes and view entry with empty catalog or tenant totals |
| history, capability/capabilities, keybindings, run/runs, op | Task-list, catalog, run-list and operation entry; no live mutation or approval claim |
| plan/chat/build, init/review/test/search, compact/diff/recap, simplify/add-dir, goal | A real client message/send turn and displayed answer; goal is local prompt metadata, not proof of an autonomous backend loop |
| clear, exit/quit, theme, queue variants, export, focus, fast, agents, logs, goal variants | No command network traffic. Export checks empty-state refusal. |
| skills, prompts, kb, cron, pipeline, image, bg, attach, mcp:reload, confirm | Explicit refusal or missing-plan notice before command transport |

The 404 fixture records the following legacy routes. These tests record
migration dependencies, not accepted served behavior. Each family still needs
an admitted producer contract and command migration or an explicit refusal.

| Commands | Current API dependency |
| --- | --- |
| graph, memory | `/api/enhanced/graph/stats`, `/api/enhanced/graph/nodes`; memory mutations also use `/api/enhanced/graph/memory/{id}` |
| ask, nl, obs, broker, kvcache | `/api/graph/ask-data`, `/api/graph/nl-query`, `/api/graph/promql`, `/api/graph/traces`, `/api/graph/broker`, `/api/graph/kvcache` |
| ingest | `/api/enhanced/extract/submit`, `/api/enhanced/extract/stream/{job_id}`, `/api/enhanced/extract/jsonl/{job_id}` |
| sdd | `/api/enhanced/sdd/constitution`, `/api/enhanced/sdd/specs`, `/api/enhanced/sdd/plans`, `/api/enhanced/sdd/tasks` |
| impact, codemap | `/api/enhanced/graph/impact/{symbol}`, `/api/codemap` |
| resources, maintenance, config | Command dispatch now refuses these legacy families before any request; admitted management adapters remain unavailable |
| model | `/models`; failed reads now remain unavailable, distinct from a successful empty registry. Served models.list admission remains open |

App startup separately requests `/api/enhanced/helpers/list_skills`. Command
request assertions start after startup settles and do not certify zero legacy
requests for the whole application. Transport, startup and backend changes are
outside this command batch. Full subcommand coverage, live producer acceptance,
autonomous goals, served model selection and complete R012.4.3.2 remain open.

Supported-read failure qualification extends the same command matrix. Mounted
fleet, MCP, tools, history, usage, capability and run commands receive HTTP 403
or a read timeout. Each displays unavailable, sends no fallback request and
permits a later `/help`. Usage now owns Escape locally, so one press restores the composer after
success, denial or timeout. After the modal keyboard repair merges, capability and run cases also press
Escape. Success and failed-read paths restore composer focus and accept `/help`.
This integrates the existing modal fix without changing its source. These cases add validation, not new implementation or completion.


### Local settings entry and legacy management boundaries

R012.4.3.1 gains `/settings`, which opens the existing SettingsScreen. Mounted
command tests search, toggle a checkbox, close with Escape and reopen persisted
settings. This proves local saved settings access, not application-wide live
application of every setting. No backend request comes from this command.

R012.2.1 distinguishes failed `/models` reads from a successful empty registry.
Missing or denied routes, timeout, invalid JSON and invalid registry shapes
raise errors in the direct client projection. The command displays one named
unavailable result for list and detail reads. Metadata remains unchanged on
success. R012.2.2 models.list, profile admission and selected-profile display
remain open; the installed registry does not expose models.list.

R012.4.1 now refuses config, resources and maintenance command families before
legacy REST dispatch. Notices name their existing route family, without
inventing operation identifiers. Listing and mutation journeys both make zero
command requests. Direct legacy client wrappers are not migrated or qualified.
Graph, memory, ingest and SDD migrations and full R012.4.3.2 acceptance remain
open. The existing app startup skills request is outside this command slice.

Model-shape review adds mounted regressions for consumed cost and tags fields.
Cost must be a mapping with finite numeric input/output values when supplied.
Tags must be a list of strings when supplied. Invalid fields produce the named
unavailable result for all three registry-read forms. Unrelated metadata is preserved.


### Focus command after sidebar keyboard navigation

R012.4.3.1 preserves composer focus after `/focus` hides or opens the sidebar.
The command reuses the existing screen action, then restores composer focus.
Ctrl+B still moves focus into sidebar tabs when opening them. Mounted real-client
regressions exercise both command spellings and the shortcut, with no command
requests or model turn. The existing dispatcher regressions remain unchanged.

Both original cases fail on untouched main 55c5aad6 at
`tests/test_registered_command_contract.py:47`: ContentTabs has focus instead
of InputTextArea. The two new real-client cases reproduce the same failure.
This command repair does not change sidebar navigation, layout or transport.

### Exact-main qualification at 992a762d

GR1080 tested commit `992a762d2a8002a712cb1601d93003ba6697ee70` in a clean,
isolated worktree. Its source tree is `27293e499dc77313c2d99b4dad3b2e119590f486`.
Python 3.14.7 used the prior pinned client/test dependencies in a new environment.
Arbora 0.1.7 used CI's explicit `--no-deps` installation policy. This does not
qualify its server dependency graph: full transitive resolution conflicts with
pinned platformdirs 4.12.2, while agent-utilities requires at least 4.13.3.
No source dependency or lock changed.

| Check | Result |
| --- | --- |
| `PYTHONPATH=. python -m pytest tests -q -n 4 --tb=short` | 1,651 passed, two optional modules skipped, one warning; six snapshots passed. Both prior `/focus` failures pass. |
| `cargo +1.96.0 test --locked --manifest-path native/agent-terminal-ui/Cargo.toml` with an isolated target directory | 166 passed, none failed or ignored. |
| `PYTHONPATH=. python -m pytest tests/test_presentation_pty.py tests/test_native_public_details_pty.py -q -ra --tb=short` | Five passed after installing pyte 0.8.2 and wcwidth 0.9.3 and setting `TUI_NATIVE_TEST_BINARY` to the exact-main executable. These cover both initially skipped modules. |
| `PYTHONPATH=. python -m pytest tests/test_app_workers.py -q -W error::pytest.PytestUnraisableExceptionWarning --tb=short` | 15 passed; the full-run warning did not reproduce. |

The unresolved warning is `PytestUnraisableExceptionWarning` while finalizing
`Conversation.add_info`, with `KeyError: '__import__'`. Pytest attributed it to
`test_on_agent_event_received_tool_call_delegated`. The isolated module result
does not establish its cause or repair; this is not warning-free qualification.

SHA-256 provenance:

| Artifact | Hash |
| --- | --- |
| `uv.lock` | `2adcac4001c4b99b7bc5ca0a3197707db179f0028062e07cdb6ace760d7aa460` |
| Native `Cargo.lock` | `2d41a2016f3574164ef163d8500d6bb71fa9372851d7a8e3081c87dfb2d7e18a` |
| Installed Arbora `METADATA` | `9157b068e779bcd1850a8dd1f91f1a7d3ba1be4e3153971b9ab8c0522bf05971` |
| Installed Arbora `RECORD` | `3ea902bc5fccc65c1e5c6c33ca3f9249d9e18980d3fc61d3753a4a4c33f551a8` |
| Native executable | `41bac7554684012147cc4b2392006e6b541b64de8541e1b8b9de03a465206840` |
| Evidence bundle | `87b72757ceaa93cd2f22d403d25e39e861c4e84696d9afff79930624b03a0062` |

Library retains `tui-992a762d-qualification.zip`, ID
`libfile_d7cef34e3c608191b8a0859f9a139326`, version 0. It contains raw results,
the final dependency freeze, source-file hashes and the warning investigation.
This receipt supports existing bounded R012.4.3.1 and R012.2.1 evidence without
changing acceptance status or test markers. It does not prove live producers,
production identity, full served parity or release performance.

## Initial history loading regression

R012.3.1 now opens its history screen before the first page read.
`tests/test_history_initial_load.py` enters `/history` through the mounted
AgentApp composer and real client transport with controlled HTTP responses.
It verifies pending-read keyboard close, duplicate-key suppression, safe reopen
and rejection of a late completion that suppresses cancellation. Denied and
malformed first reads remain visible as unavailable and can retry with R.
The tests assert only tasks/list reads and no active task or context change.
All three cases fail on main 36de5343 before the repair.
This receipt does not establish live producer, native or conversation-resume acceptance.

Cloud qualification used Python 3.12.14, Textual 8.2.8 and Arbora 0.1.7.
The 41 scoped history tests and 26 command/documentation cases passed.
`python -m pytest tests -q -n 2 --tb=short` passed 1,723 tests with four skips
and six snapshots. The same command on baseline 64d59bd6 passed 1,720 tests
with the same skips and snapshots. Both runs emitted one subprocess-finalizer
warning after its event loop closed; this repair does not resolve that warning.
The test environment used a writable UV_CACHE_DIR for the locked-install check.
All-files pre-commit and ty on both changed runtime modules passed.
Native builds, installed-service acceptance and pre-push release gates were not run.
No new acceptance row was closed.

## Installed client candidate smoke receipt

The client candidate at ce5eb8495f47bec755841c16718e124277971318 passed
Arbora's published `test_actual_tui_completes_tokenless_chat` from
7f39b8a2bb8826e5792a6981e73d4e1f2bf81525: one test passed in 22.26 seconds.
Its normally built wheel has SHA256
`632310e571a551895e392f8a8dd181a0ac63b638ae36dacebcb06c932aaf6cfa`.
An isolated disposable environment loaded installed packages, not source overlays.
The changed client modules matched that candidate's source bytes.

The test started real local Arbora and EG services with a simulated HTTP model.
It ran the installed Python headless command.
The unique rendered nonce matched the model receipt and persisted task artifact.
The test then stopped the services.
The unchanged preserved environment was not used as the candidate installation.

The older matched backend artifacts were Arbora 0.1.7, EG 2.27.5, AU 3.1.0
and connector SDK 0.2.2, using Python 3.12.14. The cached EG union server had
SHA256 `a25412230e263bc952a140c4d81ee5c276b018ee7b376646e86928d7a735c0c0`.
This is client-candidate smoke evidence against older backend artifacts.
It does not prove the history UI against a live backend, native or fullscreen operation.
Current-backend compatibility, released dependency installation and complete spec acceptance remain open.
No requirement state changed.

## Quality acceptance v1

This contract covers R015.55–R015.69. Its effective date is 2026-10-24.
This section defines required evidence, not a passing receipt.
Every command runs from the repository root against one recorded candidate commit.
The evaluator must use a clean checkout and save output outside the source tree.

### Receipt contract

Each domain receipt must include:

- Contract version, candidate commit, UTC time, operating system and architecture.
- Exact command, working-directory role, exit code and full output artifact with its digest.
- Interpreter and tool versions, dependency lock digest, hook configuration digest and resolved shared workflow commits.
- Tracked input scope, exclusions, thresholds, collected test IDs and selected test IDs.
- Counts for passed, failed, skipped and expected-failure tests, with reasons and owning requirements.
- Each finding's stable ID, domain, severity, location, owning requirement, current disposition and supporting evidence.
- Missing implementations, unavailable tools, stale vulnerability databases and incomplete evidence as explicit gaps.

The evaluator must record hook revisions from `.pre-commit-config.yaml` and tool versions from the active environments.
Shared workflows currently track `main`; record their resolved commit for the exact workflow run.
Record `python --version`, `uv --version`, `pre-commit --version`, `rustc +1.96.0 --version` and `cargo +1.96.0 --version`.
Record additional scanner versions and vulnerability database timestamps before using their results.
A tool that prints warnings needs investigation even when its exit code is zero.
No staged-only check, exclusion added for acceptance, warning suppression or no-regression comparison substitutes for this contract.
Existing configured exclusions must remain visible and receive complementary evidence where the domain includes those paths.

### Executable checks

Commands identify existing entry points unless marked planned. Their presence does not prove successful execution.
Use the pinned hook runner, `uvx --from pre-commit==4.6.2 pre-commit`, for each `pre-commit` command below.
Use the configured shared hook revision for `pipelines-hook`; record the resolved revision and installed distribution version.

| Check | Required invocation and interpretation |
|---|---|
| Commit hooks | `pre-commit run --all-files --hook-stage pre-commit`. Preserve complete output, including warnings. |
| Push hooks | `pre-commit run --all-files --hook-stage pre-push`. Dependency readiness, lock and test hooks are required. |
| Spec contract | `pre-commit run spec --all-files`; `pre-commit run spec-trailers --all-files --hook-stage manual`. Record the base revision. |
| Project structure | `pipelines-hook root-hygiene`; `pipelines-hook public-surface`; `pipelines-hook gitignore-convergence`. Inspect all tracked paths. |
| Structural census | `pipelines-hook complexity-census`; `pipelines-hook kiss-census`. Retain complete reports and their resolved threshold definitions. |
| Python execution | `uv run --frozen --extra test pytest tests -q -W error`. Run every required slow or served acceptance test too. |
| Python coverage | `uv run --frozen --extra test pytest tests --cov=agent_terminal_ui --cov-branch --cov-report=json:/tmp/tui-quality-coverage.json --cov-report=term-missing -W error`. |
| Source security | Run configured `bandit`, `detect-private-key` and `security-sanitizer` hooks with `--all-files`. Retain findings before any remediation. |
| Dependency consistency | `uv lock --check`; `pre-commit run dependency-readiness --all-files --hook-stage manual`. These are not vulnerability scans. |
| Version mirrors | `pre-commit run check-bumpversion --all-files --hook-stage pre-commit`. Installed metadata and lock-mirror comparisons still need a pinned executable gate. |
| Documentation | Planned: `mkdocs build --strict --site-dir /tmp/tui-quality-docs` after pinned documentation dependencies and the inherited theme are installed. Example and link checks remain required. |
| Native format | `cargo +1.96.0 fmt --manifest-path native/agent-terminal-ui/Cargo.toml --check`. |
| Native tests | `cargo +1.96.0 test --locked --manifest-path native/agent-terminal-ui/Cargo.toml`. |
| Native lint | `cargo +1.96.0 clippy --locked --manifest-path native/agent-terminal-ui/Cargo.toml --all-targets -- -D warnings`. |

The coverage evaluator must compute line and branch percentages separately from measured coverage data.
Each percentage must reach 80 across all tracked Python package files, including files not imported during tests.
These are new measurable targets, not a conversion of the historical score.
Do not use the combined coverage percentage, source-token heuristics, test counts or the historical score.
Record uncovered lines and branches, coverage exclusions and omitted files. Missing source files invalidate the measurement.
Native code requires a separate measured coverage report and per-requirement acceptance evidence; Python coverage does not cover native code.
The native coverage tool, pinned version and executable command remain to be implemented and recorded.
The separate line/branch threshold evaluator and tracked-file completeness check also remain to be implemented.

The dependency security gate must scan all locked Python and native dependencies against a current advisory database.
It must include runtime and test extras, transitive dependencies, registry packages and pinned source dependencies.
A lock consistency check, dependency installation or empty historical report is insufficient.
The dependency scanner selection, pinned version, exact command and raw report remain required implementation work.
Resolve all actionable findings at every severity, including R015.8's medium-severity findings.
Any disputed finding requires reproduction evidence and an explicit reviewed disposition; omission or suppression does not resolve it.

Structural census wrappers refuse unavailable scanners in CI; local skips do not establish acceptance.
Acceptance requires zero unresolved violations of the owning requirements, not merely exit code zero.
Implement missing full-tree module-size, method-count, nesting and test-structure checks before claiming the corresponding rows.
Retain shared thresholds at the recorded revision; do not introduce more permissive local limits.

### Per-domain evidence matrix

The evaluator must retain all seventeen domains, including domains without a separate legacy score row.
Each entry requires a distinct receipt with the commands above, acceptance obligations and remaining gaps.

| Domain | Required evidence and open implementation scope |
|---|---|
| Project Analysis | Project structure checks, valid package metadata, installed entry-point tests and R015.11–R015.18 documentation evidence. |
| Dependency Audit | Lock consistency, dependency readiness and complete actual vulnerability scans; scanner implementation remains required. |
| Codebase Optimization | Full structural census and R015.1–R015.7, R015.19–R015.20 measurements; implement missing structural checks. |
| Security Analysis | Source and secret scans, dependency scan, R015.8 and functional security acceptance. No severity is silently waived. |
| Test Coverage | Separate measured line and branch thresholds, native report and uncovered requirement inventory; coverage tooling gaps remain open. |
| Documentation & Governance | Strict documentation build, links, examples, license and R015.10–R015.18 evidence; implement missing link/example checks. |
| Architecture & Design Patterns | R015.21–R015.23 import boundaries, dependency seams and responsibility map; implement missing full-tree checks. |
| Concept Traceability | Spec and concept hooks plus complete R015.24–R015.27 declaration-to-source-to-test reconciliation; missing reconciliation remains open. |
| Linting & Formatting | Complete configured lint, format and type checks with no errors or warnings; native checks and excluded-path evidence included. |
| Pre-Commit Compliance | Both all-file stages, exact configured hook pins and complete logs; CI skips do not qualify omitted hooks. |
| Test Execution | Full Python and native suites, collection/outcome inventory and required served acceptance; selection or refusal-only coverage is insufficient. |
| Directory Organization | Root hygiene, tracked-file layout and module responsibility checks; inventory source and test structure, not generated artifacts. |
| UI/UX Quality | Existing R008, R012 and R014 interaction, presentation and native acceptance tests; no screenshot or heuristic replaces behavior. |
| Version Sync Analysis | Version dry-run, lock mirrors, installed metadata and R015.31–R015.33; historical reports remain outside authoritative mirrors. |
| Changelog Audit | Verify the changelog's current version, dated release sections and change entries against repository history; implement missing automated checks. |
| Pytest Quality | R015.9 and R015.34–R015.40 structural, fixture and assertion evidence; test incorrect observable results, not assertion presence. |
| Environment Variables | R015.41–R015.43 source inventory, dynamic aliases, examples, defaults and real entry-point tests; native residuals remain required. |

The existing environment, fixture, README and operator-documentation tests supply bounded evidence only.
Reuse `tests/test_environment_inventory.py`, `tests/test_fixture_isolation.py`, `tests/test_readme_navigation.py` and `tests/test_operator_documentation.py`.
Their presence or a targeted pass does not establish complete domain acceptance.
A missing full-domain check remains work to implement; do not create a test that asserts this table exists as acceptance.

### Finding inventory and aggregate acceptance

The evaluator must build the current inventory from complete scans of the candidate revision.
Use stable IDs that survive line movement; retain original report locations and links to current owning requirements.
Map every historical priority and finding to a current item, duplicate, resolved item or evidenced non-applicable item.
Keep historical provenance separate from new findings. Never invent entries to match an old total.
For each resolved item, record the fix revision and a successful reproduction or regression check.
For each duplicate or non-applicable item, record the source evidence and reviewed reason.
A missing historical item or unexplained count discrepancy is an inventory gap, not an implicit resolution.

R015.67 requires all domain criteria and the complete inventory, without averaging or compensating for failed domains.
R015.68 requires seventeen independent receipts with no omitted domain or evidence gap.
R015.69 requires no unresolved actionable finding and a complete historical-to-current reconciliation.
These clauses do not assert a new finding count, GPA or letter grade.

## Operator package qualification receipt (2026-10-24)

This batch starts from main `64d59bd6cb4ebf3611204a59b183e29523b5aa89`.
The final wheel includes main `69bed18c5896389b1fc6a03cf4203758202a0e27` plus this package change.
R015.12 checks every Python parser flag plus interactive, headless, observer,
Docker and native start instructions. Five mutations remove entry coverage.
R015.16 checks local documentation links and rejects missing or broken targets.
These are documentation contracts, not runtime or native acceptance evidence.
R015.18 checks the tracked MIT declaration and existing license text. Packaging
now includes that unchanged file; the installed-resource check compares its bytes.
Partial R015.31 evidence checks three Python version mirrors: pyproject.toml, docs/concepts.md
and the distribution entry in uv.lock. Drift and missing registrations fail.
Native manifest and lock versions agree and reject drift. The Python bumper
does not cover those files; no native version-maintenance policy was found.
R015.31 remains open for full version configuration. Historical analysis
is not a version mirror. R015.32 and R015.33 remain open.

The configured `bump2version patch --dry-run --allow-dirty --verbose` passed.
It found each registered current version and proposed the next version without
writing files, commits or tags. No release or version change occurred.

On the cloud computer, Python 3.12.14 built the wheel from tracked source plus
this batch with `uv build --offline --wheel --python` and an explicit interpreter.
Wheel SHA-256: `c4af35741b9920b4fa091781876dc4dce5ddaffc35d1de2ae03adb77fe7c082f`.
A separate environment reused cached dependency files and installed that wheel.
With TUI_TEST_INSTALLED_ENV set, the operator documentation, package metadata,
installed operator entry and environment inventory suite passed 79 tests.

R015.71 starts the real installed console script outside the checkout against
a loopback HTTP fixture. Missing and wrong fixture credentials produce HTTP 403,
exit status 1 and a refused-read message. The authorized fixture credential
produces a completed task with no artifacts, exit status 0 and unavailable
output. Each case sends exactly one tasks/get and no submission or approval.
Neither fixture credential appears in output. This proves empty task output,
not an empty catalog or conversation list. The entry fixture also verifies the
installed metadata, import location and packaged license. Without the explicit
installed environment, these tests skip and give no installed-entry proof.
Live Arbora, native parity and release performance qualification remain open.

The final source batch reconciles the quality rubric from main `69bed18c`.
Normal pre-push checks passed except pytest in the declared-dependency environment.
That run had seven failures and six collection errors from missing optional Arbora.
Their IDs exactly match the recorded unchanged-main baseline; no new IDs appeared.
All other hooks passed. This is not a fully green declared-dependency gate.
The installed-client environment retained Arbora without a dependency sync.
Its ordinary test suite passed 1,747 tests and six snapshots, with three native skips.
It emitted the existing subprocess-finalizer warning after the event loop closed.
The run used two workers, the explicit installed wheel and writable tool caches.
Only ALL_PROXY and all_proxy were unset; HTTP and HTTPS proxy settings remained.
Native skips and the warning remain qualification gaps, not passing evidence.

The native instructions now state the default bearer mode and explicit anonymous loopback configuration.
After this wording change, 36 operator checks passed and the wheel was rebuilt.
The runtime source and license bytes did not change.

## MCP loading and retry evidence (2026-10-24)

`tests/test_mcp_responsiveness.py` qualifies client presentation for R012.4.2.
Mounted AgentApp commands open a loading view before the first read and restore
composer focus on Escape. Retry clears previous rows; typed failures remain
unavailable, distinct from valid empty results. Late success and failure cannot
replace a newer refresh or continue after a client-owner change. Cancellation
suppression cannot reopen a closed screen. The command starts no model turn.
`tests/test_served_fleet_usage.py` checks mounted MCP dispatch through real
generated-client transport fixtures. These checks do not close model admission,
conversation resume, or served session and turn usage acceptance.

## Literal completion-marker regression

`TUI-RUNTIME-R012.1.1`: `tests/test_turn_completion.py` feeds A2A-normalized
artifacts and typed terminal states into the mounted app and headless runner.
Exact, embedded and split `[DONE]` text must remain content. Mounted checks
preserve processing and queued work until terminal delivery, then dispatch once.
Pending approval still precedes the queue. Headless checks retain later text
and failures, and stop at typed completion or cancellation. These fixtures do
not qualify served streaming, native parity or full mounted cancellation.

## Operator current-main reconciliation

The operator reconciliation preserved main `2ebf9ae587ad171dd859b4425d65f9f999c03eb6`.
Only appended plan and test-spec sections conflicted; both sides were retained.
Runtime files matched that main exactly. Operator tests and the four qualified criteria were unchanged.
The combined operator, environment, CLI, MCP responsiveness, completion and headless checks passed 169 tests.
This includes the actual installed entry tests against a newly built wheel.
Its SHA-256 is `11effa2a8e9b582d192fac25bba72a385121207e177cee4e2d2d03f25baee2f9`.
All packaged Python, TCSS and license bytes matched that union checkout.
The earlier full-suite receipt remains evidence for its recorded baseline, not a new full-union run.

### Python status usage regression

R012.6.2 has supporting coverage in `tests/test_status_line_usage.py`.
Mounted text distinguishes unavailable fields from supplied zero, preserves
valid token or cost values independently, and clears prior measurements.
Null, boolean, negative, non-finite and wrong-type values must not crash.
Usage and turn-end event routes exercise the real mounted main screen.
These display tests do not qualify served turn or session totals or costs;
R012.6.2 remains open.

`tests/test_status_line_layout.py` captures visible compositor text after
resize between 120, 80, 60 and 40 columns, including a 12-row terminal.
Idle and active states retain draft text and composer focus. Geometry checks
keep the conversation, composer, status and footer separate and on screen.
The status and main-screen SVG snapshots record the corrected layout.

Keyboard tests toggle the sidebar and server log at 120, 80 and 60 columns.
The existing eight-row server log still overflows a 40-column, 12-row terminal.
This slice does not qualify that combination or full presentation acceptance.

## Historical analysis preservation receipt (R015.32 and R015.33)

Base: `2ebf9ae587ad171dd859b4425d65f9f999c03eb6`. The analysis remains in
Git history at `17e010c140395735bef41dba5a896ea0000ac99e`, before its
intentional removal from the source tree. This work restores no archived report.
The original `.specify/reports/` files at
`6177f2913c08859ba5e2af27b019d1c3fcf56f95` have the same byte digests.

| Preserved report | SHA-256 |
|---|---|
| [JSON analysis](https://github.com/Knuckles-Team/agent-terminal-ui/blob/17e010c140395735bef41dba5a896ea0000ac99e/plans/spec-source-history/analysis/results.json) | `28ecaab72f6eedf75d3df249e5f05052dfb05472a32d36dc987e49dcd506521f` |
| [Markdown analysis](https://github.com/Knuckles-Team/agent-terminal-ui/blob/17e010c140395735bef41dba5a896ea0000ac99e/plans/spec-source-history/analysis/code_enhancement_report.md) | `2ba4a62a4333f2dc616e7b1315e5a28e982ba224db4929489a3acac1a22074f6` |

Run from a full Git checkout:

```bash
python -m pytest tests/test_historical_analysis.py -q -p no:randomly
```

Python 3.12.14 and pytest 9.1.1: 12 passed, no skips. The tests read the
actual Git blobs, reject altered bytes, inspect `.bumpversion.cfg`, and
reject registrations under either historical report directory. A temporary
full repository with missing evidence fails. A shallow clone or source
export explicitly skips unavailable history; that result is not preservation
acceptance. The current-version separation checks still run in those layouts.
The shared gate workflow at `a2dd609d494364daf26fdb3b18abbffa10095993`
uses `fetch-depth: 0`. A future shallow CI checkout must not treat the
unavailable-history skip as accepted preservation.

This evidence qualifies historical preservation only. It makes no current
quality claim from old scores, findings or version strings. R015.31 still
requires complete version ownership; R015.64 and the other quality acceptance
v1 rows retain their full gates. No release version or dependency changed.

The configured `pre-commit run --all-files` passed, including lint, types,
specification checks and the version dry run. The focused historical,
environment-example and shared-hook suite passed 33 tests without skips.
Full Python, native and installed qualification were outside this slice.


## Historical analysis current-main reconciliation

This reconciliation preserves main `472d0b28f60f631a184abdf4986aebacb5cf5550`
and the original historical-preservation tests. Only specification tables and
appended sections conflicted. Both source sets remain unchanged.
The operator amendment now points to the separate R015.32 and R015.33
qualification, and their task checkboxes reflect the completed preservation
checks. R015.31 remains open for complete native version-configuration coverage.

The historical, package-metadata, environment-example and shared-hook tests
passed 44 cases without skips on this union. Earlier test and wheel receipts
retain their recorded baselines; this reconciliation makes no new installed,
native or full-suite acceptance claim.


## Installed and native environment documentation (R015.42.2)

Base: `b04b208155a1f33b30b70df71c55c768c7502add`. This slice changes tests
and documentation only. It corrects the Python-only description of AGENT_THEME
and distinguishes the entry points' theme controls and NO_COLOR semantics.

`tests/test_entry_environment_pty.py` starts the real installed Python console
script and compiled native terminal outside the source checkout. Four known
palettes and an unknown name prove startup selection and tokyo-night fallback.
Absent, empty and nonempty NO_COLOR values distinguish Python presence semantics
from native nonempty-value semantics. Each case opens the log view without
host admission. Both terminals refuse and make no host-log transport request.

A Linux inotify probe watches a sentinel path supplied through AGENT_LOG_FILE.
Neither process opens the file during startup, refusal or exit. A separate
counterexample deliberately opens the file and proves that the probe detects it.
The tests also reject sentinel disclosure in terminal output.
`tests/test_entry_environment_documentation.py` checks the published claims
and native theme inventory, rejecting missing palettes and incorrect behavior.

The installed wheel comes from tracked source at the base above.
Wheel SHA-256: `3f90a423d61de012479b0c651a691ca0186974a4bfb53b6e198f2f9809e392c0`.
The isolated installation retains its dependencies; only that wheel changed.
All 76 packaged files match both the wheel and current source bytes.
The wheel build retains the existing setuptools license-deprecation warnings.
This slice makes no package-build warning-free acceptance claim.

The native tree is unchanged: `94fa72719ebf0e02b526ef91e778f85c7a674289`.
The preserved executable matches the earlier Rust 1.96.0 build receipt.
Its SHA-256 is `0cf20785126130a59200fd3dc88c8162915437bae214922c44e33f0d350ccdcb`.
No native source changed and no native rebuild was needed.

With TUI_TEST_INSTALLED_ENV and TUI_NATIVE_TEST_BINARY supplied, the entry
module passed 15 tests without skips on Linux, Python 3.12.14 and pytest 9.1.1.
The documentation module passed eight tests, including seven counterexamples.
Missing artifacts or Linux/PTY dependencies skip entry qualification and give
no acceptance evidence. Documentation checks remain available independently.
This does not qualify served theme parity, authorized host-log production,
complete native performance or the full quality acceptance v1 domains.

## Client maintenance qualification (R015.48, R015.51)

Base: `b60b72f5647dbe2662461f2d8398f2bba405455e`. This slice changes
only tests and specification records. The client, hook rules and tool pins are unchanged.
The owning implementation is `agent_terminal_ui/client.py`. Its three read
adapters remain mapped to their served operations in the client maintenance table above.

`tests/test_client_maintenance_gates.py` copies the actual hook configuration
and pyproject into temporary Git repositories. It tracks the real client path,
then invokes the configured Ruff and mypy hooks through pre-commit.
Both accept a valid function. Ruff rejects an undefined name with F821;
mypy rejects an integer returned as a string with a return-value diagnostic.
The tests reject skipped hooks, failed clean inputs and accepted wrong results.
They use populated hook environments, not replacement tool arguments or mocks.

The two enforcement tests passed without skips in 1.74 seconds.
The current-source client, transport, mounted-command, history and text-file
regressions passed 407 tests without skips in 67.46 seconds with two workers.
The exact regression command was:

```bash
python -m pytest tests/test_client_maintenance_gates.py tests/test_client_read_contracts.py tests/test_client.py tests/test_client_methods.py tests/test_served_fleet_usage.py tests/test_task_history.py tests/test_history_refresh.py tests/test_history_navigation.py tests/test_mounted_command_matrix.py tests/test_text_files.py -q -n 2 -p no:randomly
```

The package import resolved inside this worktree through an explicit PYTHONPATH.
This evidence is not an installed-wheel qualification.

Python was 3.12.14 and the pre-commit runner was 4.7.0.
Configured Ruff was 0.15.12 at `6fec9b7edb08fd9989088709d864a7826dc74e80`.
Configured mypy was 1.20.2 at `fc0f09a29bb495f4a91f00266155d6282d52485d`.
The hook configuration SHA-256 is `053413c0ab09b0f920a642867ddee61618da5a5b4171ce49357352b1086fb80f`.
The client source SHA-256 is `fb27dd8facc158d81f0458e49b9b07cc0b1e1492f9a956f2d9a3c654771a3414`.

Set TUI_TEST_PRE_COMMIT to the installed runner and PRE_COMMIT_HOME to its
populated cache before running the enforcement module. An unset runner skips
both cases and gives no acceptance evidence. Invalid supplied paths fail.
The full candidate `pre-commit run --all-files` passed, including configured Ruff and mypy.
The candidate's full all-file gate remains the primary lint and type acceptance;
temporary counterexamples prove enforcement, not current-client correctness.
No dependency or hook environment was installed for this qualification.
`tests/test_client_maintenance_documentation.py` derives the three operation
mappings from production source and checks their owning table and execution receipt.
It rejects missing or wrong mappings, narrowed commands, missing outcomes and false live-proof claims.
A fresh combined run passed all 11 enforcement and documentation cases without skips in 1.71 seconds.
R015.29.2, R015.52 and quality acceptance v1 remain open.

## Environment and tool-guard assessment (R015.54)

Source: [missing-client task at b4e5940](https://github.com/Knuckles-Team/agent-terminal-ui/blob/b4e5940acc4b21df406eeb115c0f422b0b084901/plans/spec-source-history/tasks/fix_missing_client_methods.md).
The original next step is “Consider implementing quick wins (.env.example, tool guards)”.
It is a suggestion to assess, not a defined guard implementation contract.
The source does not identify shared development hooks as the intended tool guards.

- Environment example: available under R015.43. The tracked `.env.example`
  contains only AGENT_URL and AGENT_THEME defaults and no credential. The real
  environment factory uses the loopback URL without an Authorization header.
  The file is not loaded automatically; README.md documents explicit export.
- Runtime tool guards: refusal only. `AgentClient.invoke_op` rejects approvals.*
  operations with APPROVAL_UNAVAILABLE before transport. `confirm_plan` refuses
  unsigned confirmation, including with a caller credential. Local danger
  classification and approval screens are not proof of served authorization.
- Remaining acceptance: R001.5 verifies pending display and local refusal, not
  enabled approvals. R001.3 retains signed exact-plan confirmation acceptance.
  R011.4 and R011.5 retain diff-before-write
  and command-before-run acceptance. R002.8.4 retains scoped preapproval refusal.
  This assessment does not close any of these requirements or enable tool effects.

R015.52 remains separate: its source says “Run self-improvement scripts if available”.
The existing client receipt is not a new execution of that obligation.
R015.29.1 covers shared development guards separately; it does not resolve the
source's undefined “tool guards” suggestion.

Assessment qualification used base `8ef729851afc790174422f3f33c04e9aa347d042`
and Python 3.12.14 with the current checkout explicitly on PYTHONPATH.
The following fresh bounded run passed 185 tests without skips in 1.95 seconds:

```bash
python -m pytest tests/test_source_quality.py tests/test_client.py tests/test_commands.py -q -n 2 -p no:randomly
```

The assessment test reads the original suggestion from full Git history.
It applies the actual environment example and checks authenticated production
client refusal with a recording HTTP transport. Five altered assessments reject
false guard ownership, granted approval, omitted workspace obligations and
false completion. This is source-fixture evidence, not live authorization proof.

The complete configured commit-stage `pre-commit run --all-files` passed with
pre-commit 4.7.0 and the pinned pipelines revision
`a2dd609d494364daf26fdb3b18abbffa10095993`. The first run failed to create uv's
default tool directory. Existing writable tool and cache locations resolved that error.
Hook definitions stayed unchanged. The regression rerun passed 185 tests without
skips in 1.93 seconds. This does not qualify native builds, installed wheels,
live services or the complete pre-push stage.

## Nested execution explorer acceptance

All tests below are planned; this specification change supplies no runtime acceptance.
Retain all earlier source receipts and outstanding served, native and release gates.

| Requirement | Planned proving test | Required counterexamples |
|---|---|---|
| TUI-RUNTIME-R010.11 | `tests/test_execution_explorer_contract.py::test_snapshot_identity_and_recovery` | Root task versus step ID, replay-v1 preservation, shared run IDs, foreign owners, unknown versions, replay gaps and stale snapshots. |
| TUI-RUNTIME-R010.12 | `tests/test_execution_explorer.py::test_nested_navigation` | Parent/child/grandchild, fan-in dependencies, invalid locator, narrow viewport and missing ancestor. |
| TUI-RUNTIME-R010.13 | `tests/test_execution_explorer.py::test_public_records_and_folds` | Unavailable transcript, repeated and late tool events, private fields, denied refresh and changed node binding. |
| TUI-RUNTIME-R010.14 | `tests/test_execution_explorer_served.py::test_nested_graph_journey` | Real nested producer, reconnect, concurrent branches, cancellation and two-principal isolation. |
| TUI-RUNTIME-R012.7 | `tests/test_execution_explorer_controls.py::test_active_child_target` | Wrong target, disabled capability, stale state, duplicate submit and unknown outcome after connection loss. |
| TUI-RUNTIME-R012.8 | `tests/test_execution_explorer_controls.py::test_completed_child_continuation` | Unsupported history, still-active child, unbound continuation and root-chat fallback. |
| TUI-RUNTIME-R012.9 | `tests/test_execution_explorer_served.py::test_targeted_child_controls` | Child completion during review, revoked access, cancellation race and sibling isolation. |

The served fixture must actually spawn parent, child and grandchild executions through Agent Utilities and Arbora.
It must include two parallel children and an explicit fan-in dependency.
A tree drawn from fabricated events or a screenshot is not producer proof.
Run identical topology and control scenarios through the Python and native production terminals.
Record producer and consumer revisions, distribution versions, schema digest, node identities and per-run replay cursors.
Verify keyboard-only navigation, node selection, public folds, locator reopen and return to the original composer at 40 columns.
Verify one active-child message reaches only the chosen child, not its parent, grandchild or siblings.
Complete that child, invoke the separate continuation action and verify the producer-returned continuation identity.
Disconnect after submission; reconcile without duplicate delivery or a fabricated success.
Revoke access after successful display and verify stale records and actions disappear.
Cancel the selected authorized target; verify acknowledgement, eventual state and the producer-defined impact on related executions.

### Flat graph source-contract evidence

`tests/test_execution_graph.py` covers the bounded Python slice of R010.11 and R010.12.
It mounts the production screen through the command and application entry, with the real client and transport.
Only the graph schema lookup uses the pinned source fixture; the installed invoker and digest check remain active.
Coverage includes a 40-column diamond, shared dependencies, keyboard selection, resize and close.
Negative tests cover identity, topology, evidence, bounds, refusal, credential/context changes and late results.
The missing-operation regression makes zero network requests, without a fallback or skip.
Actual installed-SDK qualification remains separate from this source fixture.
These mounted Python tests do not close R010.11 through R010.14.
Native compilation, tests and Clippy passed in hosted CI on `612def9`.
The compiled-terminal journey below must qualify the exact candidate executable.
Nested and released-stack acceptance also remain required.

## Native flat graph source-contract coverage

The native execution graph module and loopback test file use the actual Arbora
source-contract fixture. It includes non-ASCII and maximum-length Unicode keys.
The decoder tests cover typed bounds, exact run/root binding and semantic tuple identity.
They reject duplicate evidence, cycles, unknown fields and raised child capabilities.
The public-client tests require registry advertisement and matching digests.
Missing registration makes no POST.
Malformed or denied responses do not fall back to legacy routes or direct engine calls.

Inspector TestBackend cases cover the `g` mode switch, Tab selection, 40-column
scrolling, resize, search isolation, local cancellation and stale replies.
A deterministic test cancels the awaiting completion future, then resumes its retained read handle. Each
read is scoped to the full task correlation, immutable client and generation.
Python source-contract tests check fixture provenance and schema limits only;
they do not run native code. Hosted native tests and Clippy passed on `612def9`;
actual compiled-terminal qualification uses the required journey below. R010.11 through
R010.14 and R012.7 through R012.9 remain open. No older native binary qualifies
this new graph source, and the held release prerequisite is unchanged.

## Required compiled-native graph PTY journey

`tests/test_native_public_details_pty.py` runs the real binary built by the same
native CI job. Both public-details and graph journeys must pass without skips.
The graph fixture serves only loopback registry, task and graph reads; it does
not advertise `runs.get`. Verify the validated root task/context/run, diamond
rows, separate edge details, public evidence and unavailable child controls.
Exercise Tab and Shift+Tab, then resize to 40 by 24 and back.
Hold a refresh to inspect clearing, return HTTP 403, close/reopen and quit with terminal modes restored.
Request assertions reject fallback routes, credentials, effects and any step ID
used as a root task. Each screen expectation and held response has a bounded wait.

The fixture qualifies the compiled terminal and public client path only. It does
not replace native-service, released producer/SDK or nested-agent acceptance.

## Canopy and spatial presentation acceptance

R008.3 requires explicit Canopy selection, unchanged defaults, all existing
theme cycles, no-color rules, resize and a 4.5:1 text contrast floor. Exercise
the native TestBackend and production native interaction paths, then the compiled entry point.

R010.12.1 requires stable chain, diamond, disconnected and maximum-size layout;
pan bounds; selection focus; map/list switching; narrow and search fallback;
literal hostile labels; redraw stability; and clearing after denial, close,
refresh or changed binding. Existing transport guards and effect-key isolation
remain required. Compiled PTY and served qualification are separate gates.

The entry-point matrix in `tests/test_entry_environment_pty.py` includes Canopy
startup and no-color cases for both clients. It is opt-in locally; the native
CI job requires all 18 cases and the log-open probe check without skips. Build
and install the wheel from the same checkout as the native executable. Verify
isolated import provenance and installed bytes against the wheel, then retain
source and artifact hashes with JUnit results. CI wiring regressions in
`tests/test_installed_startup_ci.py` do not qualify the actual matrix. The
spatial helper and InspectorView tests require compiled native execution.
`tests/test_native_spatial_graph_pty.py` covers resize, selection, pan, search,
denial, no-color and local effect isolation through the compiled entry point.
The native CI job requires both color cases and both existing PTY journeys
without skips. See the compiled qualification receipt below.

The spatial view labels its edge filter: only the selected step's incident
dependencies appear. All nodes and exact adjacency lists remain available.
A buffer regression distinguishes crossed pairs from the fully connected graph.
Both previously used identical terminal edge cells.

The selected-edge legend identifies graph-local plan-step `depends_on` direction.
The crossing regression changes selection and checks exact predecessor/dependent lists.
It also covers no selected card without invented edges. Held horizontal
arrows share the navigation-only repeat allowance; action repeats remain ignored.


## Native resize/input readiness acceptance

R008.4 requires keys queued with resize to arrive without another key.
Keep the existing unfenced resize, End and Tab assertion. Add a bounded
controlled case that pauses the child, queues resize and navigation, then
resumes it. The expected selection must appear without sentinel input.
Always resume or reap the child during cleanup and retain termios checks.

The first Canopy hosted run passed 184 native tests and Clippy but failed the
ordinary rapid assertion. A prior graph run passed, so that result was intermittent.
[Crossterm issue 1126](https://github.com/crossterm-rs/crossterm/issues/1126)
describes the matching readiness failure. Older-binary diagnostics are not
current acceptance. R008.4.2 requires repeated compiled runs after the correction.


## Canopy compiled qualification receipt (2026-10-24)

Source [8a05dc0](https://github.com/Knuckles-Team/agent-terminal-ui/commit/8a05dc0bd03beb6034ec8ab2bc244bff8cf7ac6b)
passed [native job 121002855836](https://github.com/Knuckles-Team/agent-terminal-ui/actions/runs/40137776795/job/121002855836):
185 native tests, Clippy, checkout build and all four required PTY cases.
No required PTY case skipped. The original rapid resize assertion and six
controlled combined/split readiness cycles passed without sentinel input.
Both Canopy color modes passed map/list, selection, resize, focus, search,
denial and effect-isolation checks. Native buffer tests covered bounds,
hostile labels and the selected-edge crossing regression.

This qualifies R010.12.1.2 and R008.4.2 for the tested Linux checkout.
The prior head 6d44a03 failed three PTY cases in run 40134463396.
Keep that intermittent input failure and fixture error in the evidence history.
The receipt update also captures real terminal cells and observed colors in
bounded PTY output. Inspect those screens and repeat the compiled gate before merge.
Installed palette, cross-terminal, served hierarchy and release qualification remain open.


## Ancestor acceptance audit regression (2026-10-24)

The bounded native evidence remains valid. Completing the flat-map child must
not mark complete hierarchy navigation as qualified. R010.12.2 retains every
unmet hierarchy criterion; the parent prose remains unchanged.

Existing gate tests assert both bounded and retained children in the hierarchy rollup.
They keep broad R008, native parity, installed Canopy, R010 and hierarchy acceptance open.
They also retain R010.14 and verify the bounded native children remain qualified.
The audit is metadata validation, not evidence for the unmet hierarchy row.
Bind it only to the existing gate requirement, never to R010.12.2.

## Python bound turn receipt coverage

`TUI-RUNTIME-R012.6.3`: Test terminal task and status normalization, exact task,
context and run binding, malformed and unknown counters, safe integer bounds,
zero versus absence, empty counts and failed turns. Mounted status/history
tests must cover replacement on replay, stale-value clearing, fresh-client
tasks/get readback, refused reads and close during a pending read. Verify that
only the existing A2A methods are used and that history never changes the
active conversation. Resize from wide to 40 by 12 and back without covering
the footer or losing exact tooltip values. Keep installed producer and
session/cost acceptance open.


## Grouped source integration receipt (2026-10-25)

Source `706cd3661212` integrates Python turn receipts and native Canopy sage on
main `8eeb2bffa338`. Original source commits are `b89278b8093f` and `995a885f8f62`.
Production and test files retain their exact bytes. Both plan amendments remain.
The old generated receipt commits are not copied into this integration.

The combined checkout passes 393 focused Python tests with Python 3.12.14,
pytest 9.1.1 and Textual 8.2.8. The command uses `pytest -q` and
`--override-ini addopts=''` with these modules:

- `test_python_turn_usage`, `test_status_line_usage`, `test_status_line_layout`;
- `test_task_history`, `test_precommit_hooks`, `test_client`;
- `test_native_task_correlation`, `test_turn_completion`, `test_app_workers`;
- `test_tui_components`, `test_headless`, `test_canopy_theme`;
- `test_history_initial_load`, `test_history_navigation`, `test_history_refresh`;
- `test_theme_keyboard`, `test_installed_startup_ci`;
- `test_native_execution_graph_contract`;
- the theme-token and baseline-contrast cases in `test_app_handlers`.

Module names above refer to files under `tests/` with the `.py` extension.
The configured all-files pre-commit stage and Rust 1.96.0 format check pass.
Both enhanced spatial PTY cases collect; collection is not execution.
Imports come from this checkout, not from an installed product qualification.

Fresh native compilation, Rust tests, Clippy, all compiled PTY cases and the
installed startup matrix remain required for this exact native source.
Historical two-color receipts do not qualify the new sage rendering.
R008.3.2 and broader presentation, native parity and hierarchy acceptance stay
open. R012.6.2 still requires installed producer, served session totals and cost
acceptance. The full configured pre-push release stage was not run locally.


## R002 request-mode removal regression contract (2026-10-25)

`test_tui.py` verifies that the mounted composer, status line, settings and
command registry expose no request-mode selector. Ordinary text remains intact
through reverse-tab navigation. `test_tui_components.py` verifies that chat,
planning and implementation prompts reach A2A unchanged without routing metadata.
`test_mounted_command_matrix.py` preserves the full command inventory and
verifies that removed mode commands issue no request.
`test_cli_documentation.py` verifies headless submission without a mode and
rejects the removed flag rather than abbreviating it to `--model`.
`test_modal_keyboard_isolation.py` retains approval dismissal and focus checks;
`test_approval_policy.py` retains required permission policy coverage. Native
submission already has no request-mode controls or metadata. These regressions
qualify client behavior only, not producer inference or served task completion.

## Native-only cutover qualification (2026-10-25)

The Python/Textual implementation and its runtime-specific test bindings are
retired. Historical passing results do not qualify native behavior. Regenerate
status from current bindings; keep historical landing evidence distinct from
native verification. Missing composition, streaming, approval attachment,
context continuation, durable resume and ACP integration remain open.

`tests/test_native_headless.py` runs five compiled-command pipe/HTTP cases:
completed output, input-required refusal, auth-required refusal, changed-context
refusal and unknown submission without replay. Native CLI parser/state tests
cover option handling and terminal outcomes. These are controlled fixtures,
not deployed-service acceptance. Existing four native PTY journeys remain
mandatory. A skipped compiled-command test is unqualified, not passed.

The native wheel workflow must pass both Linux architectures, installed-wheel
provenance, help with an empty runtime PATH and all nine compiled-command tests.
Native Cargo tests, Clippy and repository gates are required before merge.
Source-only checks cannot authorize release or deployment.

## R011.14: explicit local ACP text transport

Native `tests/acp.rs` covers initialization, session binding, ordered text,
response IDs, unsupported callbacks, cancellation, EOF and frame limits.
`local_runtime` unit tests preserve flag-looking prompt data and reject mixed
local and central arguments. `tests/test_native_acp.py` exercises the compiled
`tuig` executable with scripted success, cancellation, foreign-response and
unresponsive-child cases. An unread stdout pipe must not block cancellation
or child cleanup. A separate case uses the official Python ACP 0.11.0
SDK agent with no model or tools. Required hosted checks reject skipped cases.
These tests are transport proof only. A separate source probe passed through
Arbora's actual stdio adapter, the AU loop and a synthetic FunctionModel. It used
the exact client modules in a scoped Rust harness, not the full `tuig` binary.
The probe returned `hello client`, accepted advertised close and exited zero.
Arbora was an uncommitted integration on `72fc99db`; AU used reviewed source
`3a6adb40` (upstream merge `832d317a`). Full production-binary and installed
release pairing remain pending. This is not live-provider qualification.


## R011.14 installed helper resolution

`tests/test_native_acp.py::test_native_acp_installed_helper_resolution` copies the
compiled production executable into an isolated installation directory and
starts it through an external symlink. `PATH` excludes the installation.
A sibling helper and a valid sibling symlink must complete one ACP turn, even
with a conflicting helper on `PATH`. An absent sibling must use the existing
`PATH` helper. Missing helpers, broken sibling symlinks and non-executable
siblings must fail; invalid siblings must not run a valid fallback helper.
Preserve token filtering, the invalid central endpoint and owned-child exit
checks. Hosted CI requires all thirteen ACP cases without skips. These scripted
process tests do not qualify a released backend or future optional dependency.

## Native presentation acceptance amendment (2026-10-25)

For R008, R008.1, R008.2, R008.3 and R008.3.1, the native-only decision
supersedes Python frontend coexistence and cross-frontend execution. Earlier
Python and cross-terminal receipts above remain historical evidence only.
Use current native presentation and renderer tests for their bounded claims.
Use Python PTY or gallery harnesses when they exercise the native executable.

R008.2 still requires all supported themes, full keyboard and selection
behavior, retained scrolling, no-color, reduced motion and R002 performance.
R008.3 still requires selection, resize, composer retention, theme cycling,
contrast and compiled qualification. Missing native journeys stay planned.
A deleted Python test or a native buffer test does not close those journeys.

## Native explicit-context submission

TUI-RUNTIME-R012.3.2.1 uses `native/agent-terminal-ui/tests/continuation.rs`
and `cli.rs` unit tests. `tests/test_native_continuation.py` checks the compiled
headless entry point with two fresh client processes against a wire fixture.
This fixture is not a durable backend restart test. Verify canonical IDs, one prompt, fresh turn identities
and exact context forwarding. Missing, malformed or duplicate capabilities make
zero submissions. Missing, wrong or duplicate activation echoes and changed
returned contexts leave an unknown outcome with no retry. Reject observation,
AGENT_TASK_ID and local ACP combinations. Keep actual restart proof separate.
