# TUI-RUNTIME design and integration plan

## Existing wiring and architecture

At the current public main revision, `CommandProcessor` in `agent_terminal_ui/commands.py` owns slash-command dispatch and the `/capabilities` and `/run` commands. `AgentClient` in `agent_terminal_ui/client.py` owns HTTP transport, session events and the older `/api/capabilities/*` and `/api/runs/*` routes. `agent_terminal_ui/app.py`, `screens/main.py`, `tui/input_text_area.py`, `tui/capability_palette.py` and `tui/run_inspector.py` are presentation consumers. This is the path to extend; no parallel command router, HTTP client or local GraphOS gateway should be created.

A TUI-RUNTIME-R001 implementation candidate exists on a separate Git branch, but it is not part of public main and does not establish release acceptance. It prototypes `/op`, `/confirm`, a lazy generated-client import and fail-closed approval behavior. Review and compose its exact changes rather than rebuilding the same transport from scratch. The current main package targets Python `>=3.11,<3.15`; GraphOS generated-client compatibility must be handled without raising that base floor silently.

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
| PLAN | Store only the short-lived server binding necessary for display and one confirmation. Bind to exact plan reference, op, input digest, caller/session, registry digest and expiry; let server make the final authoritative check. Clear after use or failure. |
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
