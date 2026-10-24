# TUI-RUNTIME implementation tasks

- [ ] Review the existing isolated TUI-RUNTIME-R001 source candidate against current main and this spec; preserve unrelated concurrent edits.
- [ ] Confirm Arbora's public generated registry, endpoint and A2A plan methods in an installed wheel. Align the optional client dependency and Python support matrix.
- [ ] Wire `/op` and `/confirm` through `CommandProcessor` and the single `AgentClient`; keep chat and existing read-only screens usable.
- [ ] Enforce TLS, verified caller identity, exact one-use PLAN binding and stable error handling. Keep approval/grant routes closed until Arbora's signed pending-call exchange is served and tested.
- [ ] Add the positive and negative unit, contract, Textual and installed-wheel tests in `test-spec.md`.
- [ ] Run the configured language checks; define and run CCCC, `jscpd` and Dupehound commands/thresholds or document their explicit acceptance exception. Review KISS and remove duplicate transport paths.
- [ ] Publish the exact merged TUI revision, Arbora service revision, checks and consumer receipts in `status.json`. Move to LANDED only after merge, ACCEPTED only after the served proof.

`TUI-RUNTIME-R002` (reconciling the primary chat transport with the current Arbora boundary) is not covered by the tasks above:

- [x] Select one canonical transport for the TUI's primary conversational connection to Arbora in place of the unmounted streaming and remote-procedure routes it currently expects; update `AgentClient` to that transport atomically and remove the superseded code path only after session, authentication, streaming and cancel behavior are proven by integration tests (closes `TUI-RUNTIME-R002`).

## Decomposition children (tracked)

- [ ] **TUI-RUNTIME-R001.1:** Known op and object params produce one versioned request with correct envelope
- [ ] **TUI-RUNTIME-R001.2:** Verified caller header reaches remote Arbora only over TLS
- [ ] **TUI-RUNTIME-R001.3:** One /confirm resumes exactly the issued plan
- [x] **TUI-RUNTIME-R001.4:** Typed success renders and chat remains functional
- [ ] **TUI-RUNTIME-R001.5:** Pending request is displayed; no effect is asserted
- [ ] **TUI-RUNTIME-R001.6:** Base chat works; compatible optional install enables /op
- [ ] **TUI-RUNTIME-R001.7:** Legacy screens still render or use served replacement
- [ ] **TUI-RUNTIME-R001.8:** One-shot background tool-task command extends command/client contract with Arbora preapproval binding gate

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
- [ ] **TUI-RUNTIME-R002.2:** Require Arbora to bind web_logs into the authenticated receipt or handoff. Validate mode, scope and bindings before reads; missing preference means zero reads.
- [ ] **TUI-RUNTIME-R002.3:** Define run_host_terminal and HostLogReader. Reuse the existing app and AgentClient.
- [ ] **TUI-RUNTIME-R002.4:** Subscribe only for terminal/both with bound web_logs=true. Disabled, missing and web-mode cases make zero TUI reads; chat and the required host sink continue.
- [ ] **TUI-RUNTIME-R002.5:** Reauthorize reads and reconnects. Bound data. Expose gaps. Clear denied state. Cancel only the owned reader.
- [ ] **TUI-RUNTIME-R002.6:** Prove seeded tenant isolation across mode and web_logs enabled/disabled cases on the real host, client and TUI.

Arbora producer contracts R009.2 through R009.6 and R010.7 are prerequisites. Mock-only tests do not establish them.
<!-- /spec-definition-patch -->

## 2026-10-13 Rust migration work order

1. Review these definitions under R002/R008 and record the spec-delivery PR.
2. Smallest implementation: extend existing client tests with shared wire
   fixtures for unsupported methods, task/context/run identity and disconnect.
   Keep this source-only slice independent of a Rust dependency build.
3. Arbora must serve message/stream, tasks/resubscribe and arbora.plan/confirm
   and provide identity-bound positive and refusal receipts. This is producer
   work; terminal tests cannot claim it complete.
4. After a validation slot is assigned, add the Rust view reducer and terminal
   shell, then the asynchronous transport using those fixtures. Port one production
   entry point at a time; keep Python usable until served parity passes.
5. Qualify direct access against the benchmark contract. Propose a local broker
   only with a measured benefit and principal-isolation proof. Release only
   after all existing approval, host handoff and run-surface gates pass.

Two shared validation slots are occupied by Arbora and Immich at delegation.
Do not start a broad Rust build or full-suite push hook without coordination.
Record deferred validation as deferred, never passed.

- [ ] **TUI-RUNTIME-R002.7:** Build the native discovery entry point and run its HTTP, refusal, cancellation and rendering tests.

- [ ] **TUI-RUNTIME-R008.2:** Prove full native presentation parity and the required render performance.
- [ ] **TUI-RUNTIME-R002.1.1:** Add the native task correlation model and shared wire fixture tests.
  Keep transport activation under R002.1 until served producer proof exists.

- [ ] **TUI-RUNTIME-R002.1.4:** Wire the read-only native task view and verify it through real HTTP handlers.

- [ ] **TUI-RUNTIME-R002.1.2:** Validate read-only snapshots through the authenticated native client.
- [ ] **TUI-RUNTIME-R002.1.3:** Complete the original served chat, recovery and cutover acceptance.
- [x] **TUI-RUNTIME-R002.1.3.1:** Verify one native text submission through the existing Arbora request and AU enqueue path.
- [ ] **TUI-RUNTIME-R002.1.3.2:** Complete every original served session, streaming, cancellation and recovery criterion before cutover.

- [x] **TUI-RUNTIME-R002.1.5:** Prove the original remote-cancellation criterion through the native consumer and existing producer.

## One-shot tool-task work order

- [ ] **TUI-RUNTIME-R002.8:** Complete the six consumer children after the exact Arbora payload and preapproval bindings exist.
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
- [ ] `TUI-RUNTIME-R008.2.3.1`: Python selection during startup.
- [ ] `TUI-RUNTIME-R008.2.3.2`: Remaining full served presentation and release performance acceptance.
- [ ] `TUI-RUNTIME-R002.1.3.2.1`: Bounded native read recovery.
- [ ] `TUI-RUNTIME-R002.1.3.2.2`: Remaining served chat and recovery acceptance.
- [ ] R010.8: Validate native inspector transport and integrate the production loop; retain R010.6 served acceptance separately.

- [ ] **TUI-RUNTIME-R010.9:** Attach the bounded native inspector loop; retain full served acceptance under R010.6.

- [ ] `TUI-RUNTIME-R002.1.3.2.2.1`: Bounded local task stream decoder.
- [ ] `TUI-RUNTIME-R002.1.3.2.2.2`: Remaining served stream recovery acceptance.

- [x] **TUI-RUNTIME-R002.9:** Remove the unbound file tail and unify the log refusal controls.

- [ ] `TUI-RUNTIME-R002.10`: Integrate authenticated host logs into the existing Python terminal.

- [ ] `TUI-RUNTIME-R002.11`: Attach authenticated logs to the native event loop.

- [ ] **TUI-RUNTIME-R002.1.3.2.2.3:** Attach the bounded committed terminal point-read without claiming served recovery.

- [ ] **TUI-RUNTIME-R012.1:** Render served turn events live; keep the unary path. Depends on `ARBORA-A2A-R001.4`.
- [ ] **TUI-RUNTIME-R012.2:** List and prefer Arbora model profiles. Depends on `ARBORA-A2A-R016.6`.
- [x] **TUI-RUNTIME-R012.2.1:** Replace retired registry imports with current legacy client boundary regression coverage.
- [ ] **TUI-RUNTIME-R012.2.2:** Qualify served profile discovery, preference transport and producer-selected model display. Depends on `ARBORA-A2A-R016.6`.
- [ ] **TUI-RUNTIME-R012.3:** List, resume and continue caller contexts. Depends on `ARBORA-A2A-R001.3`.
- [ ] **TUI-RUNTIME-R012.4:** Route every command to a served operation or one unavailable notice.
- [ ] **TUI-RUNTIME-R012.5:** Complete unsupported refusal and served file-part admission.
- [ ] **TUI-RUNTIME-R012.5.1:** Refuse unsupported image inputs without silent payload loss; qualify the command-to-submission boundary.
- [ ] **TUI-RUNTIME-R012.5.2:** Send bounded file parts. Depends on `ARBORA-A2A-R001.5`.
- [ ] **TUI-RUNTIME-R012.6:** Read usage through `usage.read`.

- [ ] **TUI-RUNTIME-R010.4.1:** Wire the Python current-plan command and expiring read-only view.
- [ ] **TUI-RUNTIME-R012.4.2:** Wire fleet and tenant usage reads; preserve unavailable and pagination boundaries.
- [ ] **TUI-RUNTIME-R004.1:** Consolidate spec checks while preserving stages and trailer fallback.
- [ ] **TUI-RUNTIME-R012.4.1:** Refuse unavailable management command families before transport.

- [ ] **TUI-RUNTIME-R004.2:** Preserve blocking spec coverage and wire repository checks at their shared-policy stages.

- [ ] **TUI-RUNTIME-R012.4.3:** Complete served command matrix; acceptance remains pending.
- [x] **TUI-RUNTIME-R012.4.3.1:** Qualify registered signatures, focus dispatch and mounted usage aliases.
- [ ] **TUI-RUNTIME-R012.4.3.2:** Qualify the retained full served command matrix.

- [ ] **TUI-RUNTIME-R010.4.2:** Live current-plan acceptance; acceptance remains pending.

## Source quality obligations

- [ ] **TUI-RUNTIME-R015:** Complete each child with current source and acceptance evidence.
- [ ] **TUI-RUNTIME-R015.1:** Terminal functions must meet the shared function-size checks. Source obligation: `T001`.
- [ ] **TUI-RUNTIME-R015.2:** The command processor must meet shared complexity and responsibility checks. Source obligation: `T002`.
- [ ] **TUI-RUNTIME-R015.3:** The client must meet shared complexity and responsibility checks. Source obligation: `T003`.
- [ ] **TUI-RUNTIME-R015.4:** The application event handlers must meet shared complexity checks. Source obligation: `T004`.
- [ ] **TUI-RUNTIME-R015.5:** The skill integration tests must meet shared complexity checks. Source obligation: `T005`.
- [ ] **TUI-RUNTIME-R015.6:** The input widget must meet shared complexity checks. Source obligation: `T006`.
- [ ] **TUI-RUNTIME-R015.7:** Terminal functions must meet the shared nesting-depth checks. Source obligation: `T007`.
- [ ] **TUI-RUNTIME-R015.8:** The dependency and source security scans must report no medium-severity findings. Source obligation: `T008`.
- [ ] **TUI-RUNTIME-R015.9:** Each terminal test must assert its observable result. Source obligation: `T009`.
- [ ] **TUI-RUNTIME-R015.10:** Documentation examples must match the tested terminal behavior. Source obligation: `T010`.
- [ ] **TUI-RUNTIME-R015.11:** The README must explain the terminal purpose and installation. Source obligation: `T011`.
- [ ] **TUI-RUNTIME-R015.12:** The README must cover each supported operator entry point. Source obligation: `T012`.
- [ ] **TUI-RUNTIME-R015.13:** The README must provide navigation for its documented sections. Source obligation: `T013`.
- [ ] **TUI-RUNTIME-R015.14:** The README must provide reproducible installation instructions. Source obligation: `T014`.
- [ ] **TUI-RUNTIME-R015.15:** The README must explain the terminal architecture. Source obligation: `T015`.
- [ ] **TUI-RUNTIME-R015.16:** The README must link its detailed documentation. Source obligation: `T016`.
- [ ] **TUI-RUNTIME-R015.17:** The contributor guide must describe tools, commands and source structure. Source obligation: `T017`.
- [ ] **TUI-RUNTIME-R015.18:** The repository must declare its license in a tracked license file. Source obligation: `T018`.
- [ ] **TUI-RUNTIME-R015.19:** Terminal modules must meet the shared module-size checks. Source obligation: `T019`.
- [ ] **TUI-RUNTIME-R015.20:** Terminal classes must meet the shared method-count checks. Source obligation: `T020`.
- [ ] **TUI-RUNTIME-R015.21:** The terminal must separate presentation from its served client adapter. Source obligation: `T021`.
- [ ] **TUI-RUNTIME-R015.22:** Terminal collaborators must use explicit dependency injection at test seams. Source obligation: `T022`.
- [ ] **TUI-RUNTIME-R015.23:** The terminal package must organize its public modules by responsibility. Source obligation: `T023`.
- [ ] **TUI-RUNTIME-R015.24:** The terminal must trace each declared concept to its owning implementation. Source obligation: `T024`.
- [ ] **TUI-RUNTIME-R015.25:** The terminal must resolve each orphaned concept reference. Source obligation: `T025`.
- [ ] **TUI-RUNTIME-R015.26:** Terminal tests must bind their owning contract identifiers. Source obligation: `T026`.
- [ ] **TUI-RUNTIME-R015.27:** Significant terminal functions must identify their owning contracts. Source obligation: `T027`.
- [ ] **TUI-RUNTIME-R015.28:** The terminal source must pass the configured lint checks. Source obligation: `T028`.
- [ ] **TUI-RUNTIME-R015.29:** The repository must validate its pinned formatter and dependency hook versions. Source obligation: `T029`.
- [ ] **TUI-RUNTIME-R015.29.1:** Pin the canonical shared development guards, preserve both stages and verify clean acceptance plus real refusal.
- [ ] **TUI-RUNTIME-R015.29.2:** Validate all remaining formatter and dependency hook versions; retain the broader R015.29 acceptance obligation.
- [ ] **TUI-RUNTIME-R015.30:** The terminal CLI must provide help text for its supported arguments. Source obligation: `T030`.
- [ ] **TUI-RUNTIME-R015.31:** The version configuration must cover every authoritative version mirror. Source obligation: `T031`.
- [ ] **TUI-RUNTIME-R015.32:** The preserved JSON analysis must remain historical evidence, separate from authoritative version mirrors. Source obligation: `T032`.
- [ ] **TUI-RUNTIME-R015.33:** The preserved Markdown analysis must remain historical evidence, separate from authoritative version mirrors. Source obligation: `T033`.
- [ ] **TUI-RUNTIME-R015.34:** Terminal test modules must meet the shared file-size checks. Source obligation: `T034`.
- [ ] **TUI-RUNTIME-R015.35:** Terminal test modules must meet the shared test-count checks. Source obligation: `T035`.
- [ ] **TUI-RUNTIME-R015.36:** Terminal tests must organize unit, integration and served acceptance coverage. Source obligation: `T036`.
- [ ] **TUI-RUNTIME-R015.37:** Terminal tests must provide a shared fixture entry point. Source obligation: `T037`.
- [ ] **TUI-RUNTIME-R015.38:** Terminal tests must reuse shared fixtures for common setup. Source obligation: `T038`.
- [ ] **TUI-RUNTIME-R015.39:** Each terminal test must assert its observable result. Source obligation: `T039`.
- [ ] **TUI-RUNTIME-R015.40:** Terminal tests must reject incorrect values through behavior-specific assertions. Source obligation: `T040`.
- [ ] **TUI-RUNTIME-R015.41:** The documentation must cover every supported terminal environment variable. Source obligation: `T041`.
- [ ] **TUI-RUNTIME-R015.42:** The documentation must define AGENT_LOG_FILE and AGENT_THEME behavior. Source obligation: `T042`.
- [ ] **TUI-RUNTIME-R015.43:** The repository must provide a credential-free environment configuration example. Source obligation: `T043`.
- [x] **TUI-RUNTIME-R015.44:** The client must obtain MCP configuration through the currently authorized served contract. Source obligation: `missing-client-methods checkbox 1`.
- [x] **TUI-RUNTIME-R015.45:** The client must list MCP tools through the currently authorized served contract. Source obligation: `missing-client-methods checkbox 2`.
- [x] **TUI-RUNTIME-R015.46:** The client must list conversation identifiers through the currently authorized served contract. Source obligation: `missing-client-methods checkbox 3`.
- [x] **TUI-RUNTIME-R015.47:** The client must follow TUI-RUNTIME-R012.4.2 failure semantics. Authenticated empty results differ from unavailable requests. Source obligation: `missing-client-methods checkbox 4`.
- [ ] **TUI-RUNTIME-R015.48:** The client changes must pass the configured lint and type hooks. Source obligation: `missing-client-methods checkbox 5`.
- [x] **TUI-RUNTIME-R015.49:** The client methods must carry type hints consistent with the existing code style. Source obligation: `missing-client-methods checkbox 6`.
- [x] **TUI-RUNTIME-R015.50:** The client tests must prove the three methods satisfy their contract. Source obligation: `missing-client-methods checkbox 7`.
- [ ] **TUI-RUNTIME-R015.51:** The owning client contract must record the method implementation and its acceptance evidence. Source obligation: `missing-client-methods next step 1`.
- [ ] **TUI-RUNTIME-R015.52:** The repository must run available client maintenance checks. Source obligation: `missing-client-methods next step 2`.
- [x] **TUI-RUNTIME-R015.53:** Restore Alt+Shift+T theme cycling on the main screen. Mounted tests cover every registered theme, wraparound, composer focus and text, and no-color preservation. Source obligation: `missing-client-methods next step 3`.
- [ ] **TUI-RUNTIME-R015.54:** The terminal must assess the remaining environment-example and tool-guard obligations. Source obligation: `missing-client-methods next step 4`.
- [ ] **TUI-RUNTIME-R015.55:** The terminal must score at least 80 in project analysis. Source obligation: `CHECKLIST non-FR checkbox 44`.
- [ ] **TUI-RUNTIME-R015.56:** The terminal must score at least 80 in codebase optimization. Source obligation: `CHECKLIST non-FR checkbox 45`.
- [ ] **TUI-RUNTIME-R015.57:** The terminal must score at least 80 in security analysis. Source obligation: `CHECKLIST non-FR checkbox 46`.
- [ ] **TUI-RUNTIME-R015.58:** The terminal must score at least 80 in test coverage. Source obligation: `CHECKLIST non-FR checkbox 47`.
- [ ] **TUI-RUNTIME-R015.59:** The terminal must score at least 80 in documentation & governance. Source obligation: `CHECKLIST non-FR checkbox 48`.
- [ ] **TUI-RUNTIME-R015.60:** The terminal must score at least 80 in architecture & design patterns. Source obligation: `CHECKLIST non-FR checkbox 49`.
- [ ] **TUI-RUNTIME-R015.61:** The terminal must score at least 80 in concept traceability. Source obligation: `CHECKLIST non-FR checkbox 50`.
- [ ] **TUI-RUNTIME-R015.62:** The terminal must score at least 80 in pre-commit compliance. Source obligation: `CHECKLIST non-FR checkbox 51`.
- [ ] **TUI-RUNTIME-R015.63:** The terminal must score at least 80 in test execution. Source obligation: `CHECKLIST non-FR checkbox 52`.
- [ ] **TUI-RUNTIME-R015.64:** The terminal must score at least 80 in version sync analysis. Source obligation: `CHECKLIST non-FR checkbox 53`.
- [ ] **TUI-RUNTIME-R015.65:** The terminal must score at least 80 in pytest quality. Source obligation: `CHECKLIST non-FR checkbox 54`.
- [ ] **TUI-RUNTIME-R015.66:** The terminal must score at least 80 in environment variables. Source obligation: `CHECKLIST non-FR checkbox 55`.
- [ ] **TUI-RUNTIME-R015.67:** The terminal must achieve an overall source-quality grade of at least 3.0. Source obligation: `CHECKLIST non-FR checkbox 56`.
- [ ] **TUI-RUNTIME-R015.68:** The terminal must achieve grade B or higher in all 17 source-quality domains. Source obligation: `CHECKLIST non-FR checkbox 57`.
- [ ] **TUI-RUNTIME-R015.69:** The terminal must resolve all 43 actionable source findings. Source obligation: `CHECKLIST non-FR checkbox 58`.
- [ ] **TUI-RUNTIME-R015.70:** Source-quality repairs must preserve the installed command path through `agent_terminal_ui/terminal_ui.py:10`.
- [ ] **TUI-RUNTIME-R015.71:** A served integration test must start the installed command and observe client behavior after source-quality repairs. It must distinguish a denied request from an authenticated empty result.

- [ ] `TUI-RUNTIME-R008.2.3.2.1`: Deliver native runtime baseline palette switching with focused production-handler and rendering coverage.
- [ ] `TUI-RUNTIME-R008.2.3.2.2`: Complete remaining served presentation parity and release performance qualification.

- [ ] TUI-RUNTIME-R015.30.1: qualify truthful Python help and operator examples.
- [ ] TUI-RUNTIME-R015.41.1: qualify configuration and data directory documentation.
- [ ] TUI-RUNTIME-R015.42.1: qualify theme and unbound log documentation.
- [x] **TUI-RUNTIME-R012.3.1:** Browse caller-owned tasks and read replies without claiming conversation resume.
- [ ] **TUI-RUNTIME-R012.3.2:** Qualify complete served context history and model-aware continuation after restart.
- [ ] `TUI-RUNTIME-R002.1.3.2.2.2.1`: Bounded native unary reply display.
- [ ] `TUI-RUNTIME-R008.2.3.2.2.3`: Native single-row keyboard scrolling.
- [ ] `TUI-RUNTIME-R012.6.1`: Transient native turn usage receipt.
- [ ] `TUI-RUNTIME-R002.1.3.2.2.2.2`: Bounded queued unary submission deadline.
- [ ] `TUI-RUNTIME-R002.1.3.2.2.2.3`: Explicit committed-event read enrichment.

- [ ] `TUI-RUNTIME-R002.1.3.2.2.2.4`: Remaining served stream recovery acceptance. Full served receipts remain required; local unary tests cannot close this row.
- [ ] `TUI-RUNTIME-R008.2.3.2.2.4`: Remaining served presentation qualification. Full served parity and release performance receipts remain required.
- [ ] `TUI-RUNTIME-R012.6.2`: Served turn and session token and cost display. A served fixture renders turn and session totals and unavailable values after operation refusal.

- [ ] **TUI-RUNTIME-R012.1.1:** Validate nonblocking Python submission, bounded reads, terminal replies, identity refusal and cancellation without replay.
- [ ] **TUI-RUNTIME-R012.1.2:** Retain native and full served streaming acceptance.

- [ ] **TUI-RUNTIME-R012.1.3:** Validate native nonblocking admission and bounded automatic observation without replay or cancellation interference.

- [ ] TUI-RUNTIME-R002.1.3.3: qualify explicit loopback anonymous native transport with negative credential tests and actual EG/Arbora evidence.

- [x] TUI-RUNTIME-R012.1.4: repair and test mounted tool fold updates, including inert control-only initial output.
- [x] TUI-RUNTIME-R008.2.3.2.2.1: implement and test public summary/trace folds in both terminals. Refuse malformed replacement context/run bindings for displayed tasks and require exact revalidation.
- [ ] TUI-RUNTIME-R008.2.3.2.2.2: retain full served parity and release qualification.
- [x] TUI-RUNTIME-R008.2.3.2.2.2.1: qualify the Python composer-to-fold keyboard route.
- [ ] TUI-RUNTIME-R008.2.3.2.2.2.2: retain complete presentation and release acceptance.

- [x] **TUI-RUNTIME-R012.3.1:** Add keyboard refresh of the first task page, pagination reset and recovery after refusal. Merged through PR #112.

- [x] **TUI-RUNTIME-R012.3.1:** Guard late refresh success and denial after close. Mounted cancellation regressions pass.
- [x] **TUI-RUNTIME-R012.4.2:** Qualify usage refresh ordering when an old read suppresses cancellation. Retain live usage acceptance under R012.6.
- [x] **TUI-RUNTIME-R012.4.3.3:** Refuse unsupported session and fast-mode actions; qualify mounted keyboard routes. Merged through PR #110.

- [x] **TUI-RUNTIME-R008.2.3.2.2.2.2.1:** Route held navigation keys through existing native viewports with repeated-action refusal tests.
- [ ] **TUI-RUNTIME-R008.2.3.2.2.2.2.2:** Complete retained served presentation and performance qualification.

- [x] **TUI-RUNTIME-R008.2.3.2.2.2.2.2.1:** Route vertical wheel events to the visible native viewport, preserving folds and rejecting modal or modified input.
- [ ] **TUI-RUNTIME-R008.2.3.2.2.2.2.2.2:** Complete retained full presentation qualification. Exit-modal arrows and Space are implemented with mounted focus-restoration tests; full acceptance remains open.

- [x] **TUI-RUNTIME-R012.3.1.1:** Implement and validate previous-page task navigation with fresh reads and safe async lifecycle. Independent review passed; live resume remains open.

- [x] **TUI-RUNTIME-R010.10:** Add bounded local native inspector text search with keyboard ownership, matching-line navigation and current-display tests.

- [x] **TUI-RUNTIME-R015.30.2:** Implement native CLI help before runtime setup and qualify both help aliases and argument boundaries. Executable regression fails on main and passes with the implementation.

- [x] **TUI-RUNTIME-R001.1:** Reject non-JSON numeric constants before client dispatch and parse whitespace-separated operation arguments. Focused dispatcher regressions cover refusal and recovery; the full generated-registry and transport acceptance remains separate.
- [x] **TUI-RUNTIME-R012.4.3.1:** Preserve exact names during Tab completion and align Enter, Tab and suggestion matching across casing and aliases. Mounted command tests cover these paths; full served matrix acceptance remains pending.
