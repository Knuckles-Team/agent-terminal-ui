# EH-622 test specification

| Requirement | Layer and fixture | Expected positive result | Required negative proof |
|---|---|---|---|
| EH-622.1 | Unit command parser plus `httpx.MockTransport`; installed generated registry artifact | Known op and object params produce one versioned request with correct envelope | Empty ID, malformed JSON, array input, unknown op, missing registry file and digest mismatch make zero effect requests |
| EH-622.2 | Client transport with loopback and remote URLs, fake bearer | Verified caller header reaches remote GraphOS only over TLS | Remote HTTP, absent/invalid bearer, credential in exception/log/snapshot all fail |
| EH-622.3 | A2A fake server that issues a PLAN with binding and expiry | One `/confirm` resumes exactly the issued plan | Tampered op/input/digest/subject, expired plan and replay are rejected before any effect; server also rejects stale lease |
| EH-622.4 | Mock error envelope, timeout, disconnect and malformed JSON | Typed success renders and chat remains functional | Every failure renders an error, leaves session usable and never reports success |
| EH-622.5 | Pending A2A task with `input-required` and approval metadata | Pending request is displayed; no effect is asserted | `approvals.*`, fleet grant, missing signed exchange and wrong pending-call binding are refused; enabling approval requires separate served receipt |
| EH-622.6 | Clean Python 3.11 base environment and supported optional-client environment | Base chat works; compatible optional install enables `/op` | No compatible client yields clear `CLIENT_UNAVAILABLE` and no untyped fallback |
| EH-622.7 | Route/import inventory plus Textual pilot tests | Legacy screens still render or use served replacement | No `agent_utilities.knowledge_graph` import, duplicate transport or invisible command fallback |

## Integration and acceptance receipts

1. Build and install wheels from pinned public revisions of this TUI and GraphOS; verify the generated operation registry is packaged, not only importable from a source checkout.
2. Use a reproducible local GraphOS service fixture to prove discovery, authenticated invocation, PLAN confirmation, error envelope and read-only chat continuity. A contributor must be able to run this without an organization network.
3. Run the TUI's command, client and component tests, type/lint checks, package metadata check, and the repo's CI matrix on supported Python versions. Capture exact public commit/check links in `status.json`.
4. Separately prove the served human-to-WorkItem approval binding before enabling approval routes. A pending task display is not an approval receipt.
5. Run configured CCCC, `jscpd` and Dupehound ecosystem checks if installed. They are currently absent from this repository's tracked configuration; record that as an acceptance gap until thresholds and commands are published. Review KISS against the reuse table in `plan.md`.

No manual-only proof substitutes for the negative tests. If a live identity provider is unavailable, keep approval disabled and acceptance pending rather than requiring private infrastructure to run the baseline tests.
