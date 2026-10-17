# TUI-RUNTIME implementation tasks

- [ ] Review the existing isolated TUI-RUNTIME-R001 source candidate against current main and this spec; preserve unrelated concurrent edits.
- [ ] Confirm GraphOS's public generated registry, endpoint and A2A plan methods in an installed wheel. Align the optional client dependency and Python support matrix.
- [ ] Wire `/op` and `/confirm` through `CommandProcessor` and the single `AgentClient`; keep chat and existing read-only screens usable.
- [ ] Enforce TLS, verified caller identity, exact one-use PLAN binding and stable error handling. Keep approval/grant routes closed until GraphOS's signed pending-call exchange is served and tested.
- [ ] Add the positive and negative unit, contract, Textual and installed-wheel tests in `test-spec.md`.
- [ ] Run the configured language checks; define and run CCCC, `jscpd` and Dupehound commands/thresholds or document their explicit acceptance exception. Review KISS and remove duplicate transport paths.
- [ ] Publish the exact merged TUI revision, GraphOS service revision, checks and consumer receipts in `status.json`. Move to LANDED only after merge, ACCEPTED only after the served proof.

`TUI-RUNTIME-R002` (reconciling the primary chat transport with the current GraphOS boundary) is not covered by the tasks above:

- [x] Select one canonical transport for the TUI's primary conversational connection to GraphOS in place of the unmounted streaming and remote-procedure routes it currently expects; update `AgentClient` to that transport atomically and remove the superseded code path only after session, authentication, streaming and cancel behavior are proven by integration tests (closes `TUI-RUNTIME-R002`).

## Decomposition children (tracked)

- [ ] **TUI-RUNTIME-R001.1:** Known op and object params produce one versioned request with correct envelope
- [ ] **TUI-RUNTIME-R001.2:** Verified caller header reaches remote GraphOS only over TLS
- [ ] **TUI-RUNTIME-R001.3:** One /confirm resumes exactly the issued plan
- [x] **TUI-RUNTIME-R001.4:** Typed success renders and chat remains functional
- [ ] **TUI-RUNTIME-R001.5:** Pending request is displayed; no effect is asserted
- [ ] **TUI-RUNTIME-R001.6:** Base chat works; compatible optional install enables /op
- [ ] **TUI-RUNTIME-R001.7:** Legacy screens still render or use served replacement
- [ ] **TUI-RUNTIME-R001.8:** One-shot background tool-task command extends command/client contract with GraphOS preapproval binding gate

## Structure parity with agent-webui (tracked)

- [ ] **TUI-RUNTIME-R003:** Packaged skill `agent-terminal-ui-development`
- [ ] **TUI-RUNTIME-R004:** Pre-commit spec and sprawl hooks
- [ ] **TUI-RUNTIME-R005:** Docs layout pages
- [ ] **TUI-RUNTIME-R006:** Pyproject pipelines hook sections
- [ ] **TUI-RUNTIME-R007:** Release workflow caller
- [ ] **TUI-RUNTIME-R008:** Theme tokens and no-colour fallback
- [ ] **TUI-RUNTIME-R008.1:** Wrap native discovery status and help after resize; verify startup palette and NO_COLOR with production renderer tests.
- [ ] **TUI-RUNTIME-R009:** AGENTS.md headings
- [ ] **TUI-RUNTIME-R010:** Run harness surface (rollup of 1 to 6)
- [ ] **TUI-RUNTIME-R010.1:** Run operation wiring; implement the planned positive and negative served tests.
- [ ] **TUI-RUNTIME-R010.2:** Applied configuration; implement the planned positive and negative served tests.
- [ ] **TUI-RUNTIME-R010.3:** Context and cost; implement the planned positive and negative served tests.
- [ ] **TUI-RUNTIME-R010.4:** Read-only current plan; implement the planned positive and negative served tests.
- [ ] **TUI-RUNTIME-R010.5:** Distinct terminal reasons; implement the planned positive and negative served tests.
- [ ] **TUI-RUNTIME-R010.6:** Served surface proof; implement the planned positive and negative served tests.

<!-- spec-definition-patch:r002-consumer-tasks -->
## TUI-RUNTIME-R002 consumer work order

- [ ] **TUI-RUNTIME-R002.1:** Keep the original chat path until integration proves session, authentication, streaming and cancellation.
- [ ] **TUI-RUNTIME-R002.2:** Require GraphOS to bind web_logs into the authenticated receipt or handoff. Validate mode, scope and bindings before reads; missing preference means zero reads.
- [ ] **TUI-RUNTIME-R002.3:** Define run_host_terminal and HostLogReader. Reuse the existing app and AgentClient.
- [ ] **TUI-RUNTIME-R002.4:** Subscribe only for terminal/both with bound web_logs=true. Disabled, missing and web-mode cases make zero TUI reads; chat and the required host sink continue.
- [ ] **TUI-RUNTIME-R002.5:** Reauthorize reads and reconnects. Bound data. Expose gaps. Clear denied state. Cancel only the owned reader.
- [ ] **TUI-RUNTIME-R002.6:** Prove seeded tenant isolation across mode and web_logs enabled/disabled cases on the real host, client and TUI.

GraphOS producer contracts R009.2 through R009.6 and R010.7 are prerequisites. Mock-only tests do not establish them.
<!-- /spec-definition-patch -->

## 2026-10-13 Rust migration work order

1. Review these definitions under R002/R008 and record the spec-delivery PR.
2. Smallest implementation: extend existing client tests with shared wire
   fixtures for unsupported methods, task/context/run identity and disconnect.
   Keep this source-only slice independent of a Rust dependency build.
3. GraphOS must serve message/stream, tasks/resubscribe and graphos.plan/confirm
   and provide identity-bound positive and refusal receipts. This is producer
   work; terminal tests cannot claim it complete.
4. After a validation slot is assigned, add the Rust view reducer and terminal
   shell, then the asynchronous transport using those fixtures. Port one production
   entry point at a time; keep Python usable until served parity passes.
5. Qualify direct access against the benchmark contract. Propose a local broker
   only with a measured benefit and principal-isolation proof. Release only
   after all existing approval, host handoff and run-surface gates pass.

Two shared validation slots are occupied by GraphOS and Immich at delegation.
Do not start a broad Rust build or full-suite push hook without coordination.
Record deferred validation as deferred, never passed.

- [ ] **TUI-RUNTIME-R002.7:** Build the native discovery entry point and run its HTTP, refusal, cancellation and rendering tests.

- [ ] **TUI-RUNTIME-R008.2:** Prove full native presentation parity and the required render performance.
- [ ] **TUI-RUNTIME-R002.1.1:** Add the native task correlation model and shared wire fixture tests.
  Keep transport activation under R002.1 until served producer proof exists.

- [ ] **TUI-RUNTIME-R002.1.4:** Wire the read-only native task view and verify it through real HTTP handlers.

- [ ] **TUI-RUNTIME-R002.1.2:** Validate read-only snapshots through the authenticated native client.
- [ ] **TUI-RUNTIME-R002.1.3:** Complete the original served chat, recovery and cutover acceptance.
- [x] **TUI-RUNTIME-R002.1.3.1:** Verify one native text submission through the existing GraphOS request and AU enqueue path.
- [ ] **TUI-RUNTIME-R002.1.3.2:** Complete every original served session, streaming, cancellation and recovery criterion before cutover.

- [x] **TUI-RUNTIME-R002.1.5:** Prove the original remote-cancellation criterion through the native consumer and existing producer.

## One-shot tool-task work order

- [ ] **TUI-RUNTIME-R002.8:** Complete the six consumer children after the exact GraphOS payload and preapproval bindings exist.
- [ ] **TUI-RUNTIME-R002.8.1:** Model; implement the planned test_one_shot_request_and_scope_model acceptance.
- [ ] **TUI-RUNTIME-R002.8.2:** Behavior; implement the planned test_one_shot_lifecycle_and_output acceptance.
- [ ] **TUI-RUNTIME-R002.8.3:** Wiring; implement the planned test_one_shot_uses_existing_task_transport acceptance.
- [ ] **TUI-RUNTIME-R002.8.4:** Refusal; implement the planned test_one_shot_preapproval_refusal acceptance.
- [ ] **TUI-RUNTIME-R002.8.5:** Evidence; implement the planned test_one_shot_evidence_and_reconnect acceptance.
- [ ] **TUI-RUNTIME-R002.8.6:** Hot-path proof; implement the planned test_served_one_shot_scope_and_lifecycle acceptance.

## Coding session work order

- [ ] **TUI-RUNTIME-R011:** Complete the thirteen children; retain the original served acceptance order.
- [ ] **TUI-RUNTIME-R011.1:** Model; implement the planned `test_session_model_closed_capability_set` acceptance.
- [ ] **TUI-RUNTIME-R011.2:** Behavior; implement the planned `test_capability_handlers_serve_local_host` acceptance.
- [ ] **TUI-RUNTIME-R011.3:** Behavior; implement the planned `test_path_containment_refuses_escape` acceptance.
- [ ] **TUI-RUNTIME-R011.4:** Behavior; implement the planned `test_write_shows_diff_then_applies_on_approval` acceptance.
- [ ] **TUI-RUNTIME-R011.5:** Behavior; implement the planned `test_command_displayed_before_run` acceptance.
- [ ] **TUI-RUNTIME-R011.6:** Behavior; implement the planned `test_terminal_output_streams_in_order` acceptance.
- [ ] **TUI-RUNTIME-R011.7:** Behavior; implement the planned `test_resume_reattaches_without_granting` acceptance.
- [ ] **TUI-RUNTIME-R011.8:** Wiring; implement the planned `test_requests_reach_view_from_client_stream` acceptance.
- [ ] **TUI-RUNTIME-R011.9:** Wiring; implement the planned `test_entry_point_opens_session_at_cwd` acceptance.
- [ ] **TUI-RUNTIME-R011.10:** Refusal; implement the planned `test_typed_refusals_reach_gateway` acceptance.
- [ ] **TUI-RUNTIME-R011.11:** Evidence; implement the planned `test_evidence_record_has_no_secrets` acceptance.
- [ ] **TUI-RUNTIME-R011.12:** Hot-path proof; implement the planned `test_headless_coding_session_write_and_containment` acceptance.

- [x] **TUI-RUNTIME-R010.7:** Export and test the native inspector state boundary. Served acceptance remains pending in earlier children.
- [x] **TUI-RUNTIME-R011.13:** Export and test the native approval state boundary. Earlier served requirements remain pending.
## Scoped acceptance work

- [ ] `TUI-RUNTIME-R008.2.1`: Native baseline palettes.
- [ ] `TUI-RUNTIME-R008.2.2`: Native viewport navigation.
- [ ] `TUI-RUNTIME-R008.2.3`: Remaining full presentation acceptance.
- [ ] `TUI-RUNTIME-R002.1.3.2.1`: Bounded native read recovery.
- [ ] `TUI-RUNTIME-R002.1.3.2.2`: Remaining served chat and recovery acceptance.

- [ ] `TUI-RUNTIME-R002.1.3.2.2.1`: Bounded local task stream decoder.
- [ ] `TUI-RUNTIME-R002.1.3.2.2.2`: Remaining served stream recovery acceptance.

- [x] **TUI-RUNTIME-R002.9:** Remove the unbound file tail and unify the log refusal controls.
