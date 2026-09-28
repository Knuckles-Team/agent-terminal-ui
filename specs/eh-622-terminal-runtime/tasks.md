# EH-622 implementation tasks

- [ ] Review the existing isolated EH-622 source candidate against current main and this spec; preserve unrelated concurrent edits.
- [ ] Confirm GraphOS's public generated registry, endpoint and A2A plan methods in an installed wheel; align the optional client dependency and Python support matrix.
- [ ] Wire `/op` and `/confirm` through `CommandProcessor` and the single `AgentClient`; keep chat and existing read-only screens usable.
- [ ] Enforce TLS, verified caller identity, exact one-use PLAN binding and stable error handling. Keep approval/grant routes closed until GraphOS's signed pending-call exchange is served and tested.
- [ ] Add the positive and negative unit, contract, Textual and installed-wheel tests in `test-spec.md`.
- [ ] Run the configured language checks; define and run CCCC, `jscpd` and Dupehound commands/thresholds or document their explicit acceptance exception. Review KISS and remove duplicate transport paths.
- [ ] Publish the exact merged TUI revision, GraphOS service revision, checks and consumer receipts in `status.json`; move to LANDED only after merge, ACCEPTED only after the served proof.
