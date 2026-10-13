# TUI-RUNTIME test specification

| Requirement | Layer and fixture | Expected positive result | Required negative proof |
|---|---|---|---|
| TUI-RUNTIME-R001.1 | Unit command parser plus `httpx.MockTransport`; installed generated registry artifact | Known op and object params produce one versioned request with correct envelope | Empty ID, malformed JSON, array input, unknown op, missing registry file and digest mismatch make zero effect requests |
| TUI-RUNTIME-R001.2 | Client transport with loopback and remote URLs, fake bearer | Verified caller header reaches remote GraphOS only over TLS | Remote HTTP, absent/invalid bearer, credential in exception/log/snapshot all fail |
| TUI-RUNTIME-R001.3 | A2A fake server that issues a PLAN with binding and expiry | One `/confirm` resumes exactly the issued plan | Tampered op/input/digest/subject, expired plan and replay are rejected before any effect; server also rejects stale lease |
| TUI-RUNTIME-R001.4 | Mock error envelope, timeout, disconnect and malformed JSON | Typed success renders and chat remains functional | Every failure renders an error, leaves session usable and never reports success |
| TUI-RUNTIME-R001.5 | Pending A2A task with `input-required` and approval metadata | Pending request is displayed. No effect is asserted | `approvals.*`, fleet grant, missing signed exchange and wrong pending-call binding are refused. Enabling approval requires separate served receipt |
| TUI-RUNTIME-R001.6 | Clean Python 3.11 base environment and supported optional-client environment | Base chat works. Compatible optional install enables `/op` | No compatible client yields clear `CLIENT_UNAVAILABLE` and no untyped fallback |
| TUI-RUNTIME-R001.7 | Route/import inventory plus Textual pilot tests | Legacy screens still render or use served replacement | No `agent_utilities.knowledge_graph` import, duplicate transport or invisible command fallback |

## Integration and acceptance receipts

1. Build and install wheels from pinned public revisions of this TUI and GraphOS. Verify the generated operation registry is packaged, not only importable from a source checkout.
2. Use a reproducible local GraphOS service fixture to prove discovery, authenticated invocation, PLAN confirmation, error envelope and read-only chat continuity. A contributor must be able to run this without an organization network.
3. Run the TUI's command, client and component tests, type/lint checks, package metadata check, and the repo's CI matrix on supported Python versions. Capture exact public commit/check links in `status.json`.
4. Separately prove the served human-to-WorkItem approval binding before enabling approval routes. A pending task display is not an approval receipt.
5. Run configured CCCC, `jscpd` and Dupehound ecosystem checks if installed. They are currently absent from this repository's tracked configuration. Record that as an acceptance gap until thresholds and commands are published. Review KISS against the reuse table in `plan.md`.

No manual-only proof substitutes for the negative tests. If a live identity provider is unavailable, keep approval disabled and acceptance pending rather than requiring private infrastructure to run the baseline tests.

## Structure parity rows

| Requirement | Layer and fixture | Expected positive result | Required negative proof |
|---|---|---|---|
| TUI-RUNTIME-R003 | File-level unit test in `tests/test_skill_package.py` | Wheel contains the skill | Skill missing from wheel fails |
| TUI-RUNTIME-R004 | File-level unit test in `tests/test_precommit_hooks.py` | All five hook ids present | A missing id fails |
| TUI-RUNTIME-R005 | File-level unit test in `tests/test_docs_layout.py` | Four pages exist and are in nav | A page absent from nav fails |
| TUI-RUNTIME-R006 | File-level unit test in `tests/test_precommit_hooks.py` | Both sections present | A missing section fails |
| TUI-RUNTIME-R007 | File-level unit test in `tests/test_docs_layout.py` | Workflow calls pipelines at main | A SHA pin fails |
| TUI-RUNTIME-R008 | File-level unit test in `tests/test_app_handlers.py` | Default theme and no-colour fallback hold | An unknown theme name falls back, not crashes |
| TUI-RUNTIME-R009 | File-level unit test in `tests/test_docs_layout.py` | Four headings present | A missing heading fails |

## Planned run-surface acceptance

These tests are planned, not execution receipts. Each test must bind its exact requirement ID.
Each case must enter the production UI, existing client, and a served GraphOS operation fixture.
A mocked widget value alone must not count as served evidence.

| Requirement | Planned test | Positive served requirement | Negative served requirement |
|---|---|---|---|
| TUI-RUNTIME-R010.1 | `tests/test_run_inspector_contract.py::test_run_read_uses_graphos_operations` | A selected run must render through the served operation and existing client. | Absent registration, timeout or denial must display unavailable without direct engine calls. |
| TUI-RUNTIME-R010.2 | `tests/test_run_inspector_contract.py::test_harness_config_shown` | A committed configuration must retain its reference and values through the client. | Missing or inaccessible configuration must not use defaults or the latest configuration. |
| TUI-RUNTIME-R010.3 | `tests/test_run_inspector_contract.py::test_context_and_cost_shown` | Measured zero must render as zero; aggregate cost must retain its solved-task label. | Null values must display unavailable; zero-solved abstention must not render zero cost. |
| TUI-RUNTIME-R010.4 | `tests/test_run_inspector_contract.py::test_plan_read_only` | A fresh matching snapshot must preserve item order, revision and AU statuses. | Expired, wrong-run, regressing or unavailable snapshots must reveal no items or edit controls. |
| TUI-RUNTIME-R010.5 | `tests/test_run_inspector_contract.py::test_termination_reasons_distinct` | Each of final_answer, context_overflow, stuck, step_budget and error must have its own label. | Unknown or missing reasons must display unavailable; overflow and stuck must not collapse to generic failure. |
| TUI-RUNTIME-R010.6 | `tests/test_run_inspector_contract.py::test_run_surface_end_to_end` | A served fixture must render summary, configuration, context, cost and an available plan. | Denied reads after success must clear prior protected values; the UI must stay responsive without fabricated data. |

<!-- spec-definition-patch:r002-consumer-tests -->
## TUI-RUNTIME-R002 acceptance matrix

The served acceptance uses the normal mode selector, public adapter, authenticated GraphOS reader and production TUI. Mocks may support unit tests. They cannot replace this path.

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
