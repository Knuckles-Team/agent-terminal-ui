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

## Structure parity with agent-webui (tracked)

- [ ] **TUI-RUNTIME-R003:** Packaged skill `agent-terminal-ui-development`
- [ ] **TUI-RUNTIME-R004:** Pre-commit spec and sprawl hooks
- [ ] **TUI-RUNTIME-R005:** Docs layout pages
- [ ] **TUI-RUNTIME-R006:** Pyproject pipelines hook sections
- [ ] **TUI-RUNTIME-R007:** Release workflow caller
- [ ] **TUI-RUNTIME-R008:** Theme tokens and no-colour fallback
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
