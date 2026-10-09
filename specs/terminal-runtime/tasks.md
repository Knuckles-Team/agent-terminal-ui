# TUI-RUNTIME-001 implementation tasks

- [ ] Review the existing isolated TUI-RUNTIME-R001 source candidate against current main and this spec; preserve unrelated concurrent edits.
- [ ] Confirm GraphOS's public generated registry, endpoint and A2A plan methods in an installed wheel; align the optional client dependency and Python support matrix.
- [ ] Wire `/op` and `/confirm` through `CommandProcessor` and the single `AgentClient`; keep chat and existing read-only screens usable.
- [ ] Enforce TLS, verified caller identity, exact one-use PLAN binding and stable error handling. Keep approval/grant routes closed until GraphOS's signed pending-call exchange is served and tested.
- [ ] Add the positive and negative unit, contract, Textual and installed-wheel tests in `test-spec.md`.
- [ ] Run the configured language checks; define and run CCCC, `jscpd` and Dupehound commands/thresholds or document their explicit acceptance exception. Review KISS and remove duplicate transport paths.
- [ ] Publish the exact merged TUI revision, GraphOS service revision, checks and consumer receipts in `status.json`; move to LANDED only after merge, ACCEPTED only after the served proof.

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
